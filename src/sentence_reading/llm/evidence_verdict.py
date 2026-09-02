"""
design/169l L0 — cache-level figure/artifact verdict rules (pure functions).

Used by scripts/evidence_verdict.py and scripts/track_translate.py.
No adb/GCS I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _parse_ts(ts: str) -> datetime | None:
    s = (ts or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _delta_s(a: str, b: str) -> float | None:
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None or tb is None:
        return None
    return (tb - ta).total_seconds()


def _safe_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@dataclass
class CacheTimeline:
    cache_id: str
    events: list[dict] = field(default_factory=list)

    @classmethod
    def from_events(cls, cache_id: str, events: list[dict]) -> CacheTimeline:
        cid = (cache_id or "").strip()
        rows = [o for o in events if (o.get("cache_id") or "").strip() == cid] if cid else list(events)
        return cls(
            cache_id=cid,
            events=sorted(rows, key=lambda o: o.get("ts") or ""),
        )

    def by_kind(self, kind: str) -> list[dict]:
        return [o for o in self.events if (o.get("kind") or "") == kind]

    def last_of(self, kind: str) -> dict | None:
        hits = self.by_kind(kind)
        return hits[-1] if hits else None


def _latest_open_summary(tl: CacheTimeline) -> dict | None:
    hits = tl.by_kind("open_ko_summary")
    return hits[-1] if hits else None


def _open_figure_file_rel_gap(tl: CacheTimeline) -> bool | None:
    """True if open summary shows file rel count below figure count."""
    o = _latest_open_summary(tl)
    if not o:
        return None
    d = o.get("details") or {}
    fig_n = _safe_int(d.get("figure_n"), -1)
    rel_n = d.get("figure_file_rel_n")
    if rel_n is None:
        return None
    rel_i = _safe_int(rel_n, -1)
    if fig_n < 0 or rel_i < 0:
        return None
    return fig_n > 0 and rel_i < fig_n


def _has_bad_file_rel_near_open(tl: CacheTimeline, *, window_s: float = 300.0) -> bool:
    o = _latest_open_summary(tl)
    if not o:
        return False
    open_ts = o.get("ts") or ""
    for ev in tl.events:
        if (ev.get("kind") or "") != "figure_data_url_miss":
            continue
        d = ev.get("details") or {}
        if str(d.get("reason") or "") != "bad_file_rel":
            continue
        dt = _delta_s(open_ts, ev.get("ts") or "")
        if dt is not None and 0 <= dt <= window_s:
            return True
        dt_before = _delta_s(ev.get("ts") or "", open_ts)
        if dt_before is not None and 0 <= dt_before <= window_s:
            return True
    return False


def _figure_meta_write_broken(tl: CacheTimeline) -> bool:
    w = tl.last_of("figure_meta_write")
    if not w:
        return False
    if w.get("ok") is False:
        return True
    d = w.get("details") or {}
    fig_n = _safe_int(d.get("session_fig_n"), 0)
    rel_n = _safe_int(d.get("file_rel_n"), 0)
    return fig_n > 0 and rel_n < fig_n


def _figure_window_empty_recent(tl: CacheTimeline, *, min_empty: int = 1) -> bool:
    hits = tl.by_kind("figure_window_empty")
    if not hits:
        return False
    last = hits[-1]
    d = last.get("details") or {}
    empty_n = _safe_int(d.get("empty_n"), 0)
    session_n = _safe_int(d.get("session_n"), 0)
    if empty_n >= min_empty and session_n > 0:
        return True
    return session_n > 0 and last.get("ok") is False


def _figure_read_stuck(tl: CacheTimeline, *, streak: int = 3) -> bool:
    hits = tl.by_kind("figure_window_res")
    if len(hits) < streak:
        return False
    tail = hits[-streak:]
    fig_n = 0
    o = _latest_open_summary(tl)
    if o:
        fig_n = _safe_int((o.get("details") or {}).get("figure_n"), 0)
    if fig_n <= 0:
        # infer from empty server events
        ew = tl.last_of("figure_window_empty")
        if ew:
            fig_n = _safe_int((ew.get("details") or {}).get("session_n"), 0)
    if fig_n <= 0:
        return False
    for ev in tail:
        d = ev.get("details") or {}
        empty_n = _safe_int(d.get("empty_n"), 0)
        window_n = _safe_int(d.get("window_n"), 0)
        if empty_n <= 0 and not (ev.get("ok") is False):
            return False
        if window_n > 0 and empty_n >= window_n:
            continue
        if empty_n <= 0:
            return False
    return True


def _translate_done_for_cache(tl: CacheTimeline) -> bool:
    for ev in tl.by_kind("progress_view"):
        pct = ev.get("percent")
        if pct is None:
            pct = (ev.get("details") or {}).get("percent")
        if _safe_int(pct, -1) >= 100:
            return True
    o = _latest_open_summary(tl)
    if not o:
        return False
    d = o.get("details") or {}
    sent_n = _safe_int(d.get("sentence_n"), 0)
    ko_s = _safe_int(d.get("ko_sentence_n"), 0)
    ko_f = _safe_int(d.get("ko_figure_n"), 0)
    fig_n = _safe_int(d.get("figure_n"), 0)
    return sent_n > 0 and ko_s >= sent_n and (fig_n == 0 or ko_f >= fig_n)


def _preserve_gap(tl: CacheTimeline) -> bool:
    if tl.by_kind("figure_preserve_miss"):
        return True
    if tl.by_kind("figure_preserve_skip"):
        return True
    reg = tl.last_of("figure_meta_regress")
    if reg:
        d = reg.get("details") or {}
        if _safe_int(d.get("prev_file_rel_n"), 0) > 0:
            return True
    w = tl.last_of("figure_meta_write")
    if w and w.get("ok") is False:
        d = w.get("details") or {}
        if _safe_int(d.get("prior_png_n"), 0) > 0 and _safe_int(d.get("preserved_n"), 0) == 0:
            return True
    # L0 heuristic: gen bump then bad_file_rel without vision_write_figure after bump
    derive = tl.by_kind("artifact_derive")
    if not derive:
        return False
    last_derive = derive[-1]
    gen = _safe_int((last_derive.get("details") or {}).get("gen"), 0)
    derive_ts = last_derive.get("ts") or ""
    if gen < 2:
        return False
    has_vision_after = False
    for ev in tl.events:
        if (_delta_s(derive_ts, ev.get("ts") or "") or -1) < 0:
            continue
        if (ev.get("kind") or "") != "artifact_observe":
            continue
        act = str((ev.get("details") or {}).get("activity") or "")
        if act == "vision_write_figure":
            has_vision_after = True
            break
    if has_vision_after:
        return False
    if _has_bad_file_rel_near_open(tl, window_s=600.0):
        o = _latest_open_summary(tl)
        if o and (_delta_s(derive_ts, o.get("ts") or "") or 999) >= 0:
            return True
    return False


def figure_meta_broken(tl: CacheTimeline) -> bool:
    gap = _open_figure_file_rel_gap(tl)
    if gap is True:
        return True
    if _figure_meta_write_broken(tl):
        return True
    if _has_bad_file_rel_near_open(tl):
        return True
    if _figure_window_empty_recent(tl):
        o = _latest_open_summary(tl)
        fig_n = _safe_int((o.get("details") or {}).get("figure_n"), 0) if o else 0
        if fig_n > 0:
            return True
    return False


def compute_figure_verdicts(tl: CacheTimeline) -> list[str]:
    """169l figure/artifact verdict strings for one cache_id timeline."""
    if not tl.cache_id or not tl.events:
        return []

    out: list[str] = []

    if figure_meta_broken(tl):
        o = _latest_open_summary(tl)
        d = (o or {}).get("details") or {}
        fig_n = _safe_int(d.get("figure_n"), 0)
        rel_n = d.get("figure_file_rel_n")
        if rel_n is not None:
            out.append(
                f"figure_meta_broken: file_rel { _safe_int(rel_n, 0)}/{fig_n}"
            )
        else:
            out.append("figure_meta_broken: bad_file_rel or figure_window_empty")
    if tl.last_of("figure_meta_regress"):
        reg = tl.last_of("figure_meta_regress") or {}
        d = reg.get("details") or {}
        out.append(
            "figure_meta_regress: "
            f"{d.get('prev_file_rel_n')}→{d.get('new_file_rel_n')} gen {d.get('gen_prev')}→{d.get('gen_new')}"
        )
    if _preserve_gap(tl):
        out.append("preserve_gap: prior PNG not linked into meta after save")
    if _figure_read_stuck(tl):
        out.append("figure_read_stuck: repeated empty figure_window_res")
    if _translate_done_for_cache(tl) and figure_meta_broken(tl):
        out.append("translate_ok_figure_broken: KO complete but PNG meta/read fail")

    return out


def figure_last_events(tl: CacheTimeline, *, limit: int = 8) -> list[str]:
    kinds = {
        "figure_meta_write",
        "figure_meta_regress",
        "figure_preserve_miss",
        "figure_preserve_skip",
        "figure_data_url_miss",
        "figure_window_empty",
        "figure_window_res",
        "artifact_derive",
        "open_ko_summary",
        "ingest_integrity_violation",
    }
    lines: list[str] = []
    for ev in tl.events:
        k = ev.get("kind") or ""
        if k not in kinds:
            continue
        ts_short = (ev.get("ts") or "")[11:19]
        d = ev.get("details") or {}
        if k == "figure_data_url_miss":
            lines.append(f"{ts_short} {k} reason={d.get('reason')}")
        elif k == "figure_window_empty":
            lines.append(
                f"{ts_short} {k} empty_n={d.get('empty_n')} session_n={d.get('session_n')}"
            )
        elif k == "figure_window_res":
            lines.append(
                f"{ts_short} {k} empty_n={d.get('empty_n')} window_n={d.get('window_n')}"
            )
        elif k == "artifact_derive":
            lines.append(f"{ts_short} {k} gen={d.get('gen')} activity={d.get('activity')}")
        elif k == "open_ko_summary":
            lines.append(
                f"{ts_short} {k} ko_f={d.get('ko_figure_n')}/{d.get('figure_n')} "
                f"file_rel={d.get('figure_file_rel_n', '?')}"
            )
        elif k == "figure_meta_write":
            lines.append(
                f"{ts_short} {k} ok={ev.get('ok')} file_rel={d.get('file_rel_n')}/{d.get('session_fig_n')}"
            )
        else:
            lines.append(f"{ts_short} {k} {d.get('code') or d.get('reason') or ''}".strip())
    return lines[-limit:]


def compute_cache_verdicts(
    cache_id: str,
    events: list[dict],
) -> tuple[list[str], list[str]]:
    """Return (verdicts, last_figure_event_lines)."""
    tl = CacheTimeline.from_events(cache_id, events)
    verdicts = compute_figure_verdicts(tl)
    last = figure_last_events(tl)
    return verdicts, last
