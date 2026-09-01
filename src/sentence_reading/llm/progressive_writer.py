"""design/169j — translate progressive cold path off ThreadPool workers.

Workers only mutate hot maps / enqueue. Pack, partial publish, durable
``_save_payload``, and GCS happen on a single writer thread with DropOldest
coalesce + durable debounce + ``flush()`` on phase exit.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger("sentence_reading.progressive_writer")

_DEFAULT_MAXSIZE = 48
_DEFAULT_DEBOUNCE_S = 3.0


def _emit_writer_checkpoint(
    checkpoint: str,
    *,
    job_id: str = "",
    cache_id: str = "",
    owner_uid: str = "",
    trace_id: str = "",
    elapsed_ms: int | None = None,
    queue_depth: int | None = None,
    ok: bool = True,
) -> None:
    """design/169j — never raises; no paper text."""
    try:
        from sentence_reading.llm.translate_section import _emit_checkpoint

        kwargs: dict[str, Any] = {
            "job_id": job_id,
            "cache_id": cache_id,
            "owner_uid": owner_uid,
            "trace_id": trace_id,
            "ok": ok,
        }
        if elapsed_ms is not None:
            kwargs["elapsed_ms"] = int(elapsed_ms)
        if queue_depth is not None:
            # reuse remaining as queue depth signal (sensor only)
            kwargs["remaining"] = int(queue_depth)
        _emit_checkpoint(checkpoint, blocked_on="progressive_writer", **kwargs)
    except Exception:  # noqa: BLE001
        log.debug("progressive writer checkpoint failed", exc_info=True)


class ProgressiveWriter:
    """Bounded publish/durable queue for one translate phase.

    Tokens are coalesced: draining the queue runs at most one publish + optional
    durable per wake. Overflow drops oldest (``writer_drop``).
    """

    def __init__(
        self,
        *,
        publish_fn: Callable[[], None],
        durable_fn: Callable[[], None] | None = None,
        maxsize: int = _DEFAULT_MAXSIZE,
        debounce_s: float = _DEFAULT_DEBOUNCE_S,
        job_id: str = "",
        cache_id: str = "",
        owner_uid: str = "",
        trace_id: str = "",
    ) -> None:
        self._publish_fn = publish_fn
        self._durable_fn = durable_fn
        self._q: queue.Queue[str] = queue.Queue(maxsize=max(8, int(maxsize)))
        self._stop = threading.Event()
        self._flush_done = threading.Event()
        self._durable_dirty = False
        self._last_durable_mono = 0.0
        self._debounce_s = max(0.5, float(debounce_s))
        self._job_id = str(job_id or "")
        self._cache_id = str(cache_id or "")
        self._owner_uid = str(owner_uid or "")
        self._trace_id = str(trace_id or "")
        self._drops = 0
        self._enqueue_n = 0
        self._thread = threading.Thread(
            target=self._run,
            name=f"asr-prog-writer-{self._job_id[:12] or 'anon'}",
            daemon=True,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def _ids(self) -> dict[str, str]:
        return {
            "job_id": self._job_id,
            "cache_id": self._cache_id,
            "owner_uid": self._owner_uid,
            "trace_id": self._trace_id,
        }

    def _note_enqueue(self) -> None:
        self._enqueue_n += 1
        # Sample: first + every 8th (design/169j — avoid evidence flood).
        if self._enqueue_n == 1 or self._enqueue_n % 8 == 0:
            _emit_writer_checkpoint(
                "on_item_enqueue",
                queue_depth=self._q.qsize(),
                **self._ids(),
            )

    def enqueue_publish(self, *, want_durable: bool = False) -> None:
        """Non-blocking. Never runs cold I/O on the caller thread."""
        if want_durable:
            self._durable_dirty = True
        if not self._started:
            self.start()
        token = "durable" if want_durable else "publish"
        try:
            self._q.put_nowait(token)
            self._note_enqueue()
        except queue.Full:
            dropped = False
            try:
                self._q.get_nowait()
                dropped = True
            except queue.Empty:
                pass
            if dropped:
                self._drops += 1
                _emit_writer_checkpoint(
                    "writer_drop", queue_depth=self._q.qsize(), **self._ids()
                )
            try:
                self._q.put_nowait(token)
                self._note_enqueue()
            except queue.Full:
                self._drops += 1
                _emit_writer_checkpoint(
                    "writer_drop", queue_depth=self._q.qsize(), **self._ids()
                )

    def flush(self, *, timeout_s: float = 45.0) -> bool:
        """Drain queue, force one publish + durable, stop writer. Phase-exit only."""
        if not self._started:
            # Still run cold once on caller if never started (tiny jobs).
            return self._run_cold(force_durable=True)
        self._durable_dirty = True
        self._flush_done.clear()
        try:
            self._q.put_nowait("flush")
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait("flush")
            except queue.Full:
                pass
        self._stop.set()
        ok = self._flush_done.wait(timeout=max(1.0, float(timeout_s)))
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        _emit_writer_checkpoint(
            "writer_flush",
            ok=ok,
            queue_depth=self._q.qsize(),
            **self._ids(),
        )
        return ok

    def _drain_tokens(self) -> tuple[bool, bool]:
        """Return (want_publish, want_flush)."""
        want_publish = False
        want_flush = False
        while True:
            try:
                tok = self._q.get_nowait()
            except queue.Empty:
                break
            if tok == "flush":
                want_flush = True
                want_publish = True
            else:
                want_publish = True
                if tok == "durable":
                    self._durable_dirty = True
        return want_publish, want_flush

    def _run_cold(self, *, force_durable: bool) -> bool:
        t0 = time.monotonic()
        ok = True
        try:
            self._publish_fn()
        except Exception as exc:  # noqa: BLE001
            ok = False
            log.warning("progressive publish failed: %s", type(exc).__name__)
        do_durable = False
        if self._durable_fn is not None:
            if force_durable:
                do_durable = True
            elif self._durable_dirty and (
                time.monotonic() - self._last_durable_mono
            ) >= self._debounce_s:
                do_durable = True
        if do_durable:
            try:
                self._durable_fn()
                self._durable_dirty = False
                self._last_durable_mono = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                ok = False
                log.warning("progressive durable failed: %s", type(exc).__name__)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        _emit_writer_checkpoint(
            "writer_done",
            elapsed_ms=elapsed_ms,
            ok=ok,
            queue_depth=self._q.qsize(),
            **self._ids(),
        )
        return ok

    def _run(self) -> None:
        while not self._stop.is_set() or not self._q.empty():
            want_publish, want_flush = False, False
            try:
                tok = self._q.get(timeout=0.4)
                if tok == "flush":
                    want_flush = True
                    want_publish = True
                else:
                    want_publish = True
                    if tok == "durable":
                        self._durable_dirty = True
                more_pub, more_flush = self._drain_tokens()
                want_publish = want_publish or more_pub
                want_flush = want_flush or more_flush
            except queue.Empty:
                # Idle: maybe debounce durable without a new publish signal.
                if self._durable_dirty and self._durable_fn is not None:
                    if (time.monotonic() - self._last_durable_mono) >= self._debounce_s:
                        self._run_cold(force_durable=True)
                if self._stop.is_set():
                    break
                continue
            if want_publish:
                self._run_cold(force_durable=want_flush)
            if want_flush:
                self._flush_done.set()
                break
        # Final drain after stop
        more_pub, _ = self._drain_tokens()
        if more_pub or self._durable_dirty:
            self._run_cold(force_durable=True)
        self._flush_done.set()
