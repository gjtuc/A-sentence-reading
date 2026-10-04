"""Measure the 30% shared-symbol rule on the 619 human takes.

A reference sound matches when every symbol the native reading gives at least
0.30 (blank excluded, raw softmax, mean over the aligned frames) is also at
least 0.30 on the reader's audio in that same sound's frames.

Two questions, counted rather than guessed:

  crowded   the native sound has two or more symbols at >= 0.30. A clear
            reading of the winner can still fail the rule.
  empty     the native sound has no symbol at >= 0.30.

Blank is not a symbol and is not counted. No paper text and no symbols are
printed.

    python scripts/share30_probe.py
    python scripts/share30_probe.py --limit 1
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import _MIN_PHONES, split_phone_units  # noqa: E402
from sentence_reading.llm.sound_align import align  # noqa: E402

import human_takes_probe as htp  # noqa: E402
import timing_spread_probe as wide  # noqa: E402

THR = 0.30
CLEAR = 0.70
ROOT = pathlib.Path(__file__).resolve().parent.parent
NATIVE_PATH = ROOT / ".cache" / "share30_native.json"
USER_PATH = ROOT / ".cache" / "share30_user.jsonl"
WIDE = ROOT / ".cache" / "human_takes_wide.json"
REFS = ROOT / ".cache" / "human_refs_tokens.json"


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def forward(m, pcm, rate):
    values = m.fe(pcm, sampling_rate=rate, return_tensors="pt").input_values
    with m.torch.no_grad():
        logits = m.model(values).logits[0]
    return m.torch.log_softmax(logits, dim=-1)


def land(m, logp, symbols: list[str]):
    """Frame span of each symbol, or None if the sequence cannot sit on the audio."""
    ids = {s: i for i, s in m.inv.items()}
    flat = [ids[s] for s in symbols if s in ids]
    if len(flat) != len(symbols) or not flat:
        return None
    wanted = sorted(set(flat) | {m.pad})
    column = {tid: i for i, tid in enumerate(wanted)}
    rows = logp[:, wanted].tolist()
    spans = align(rows, [column[t] for t in flat], blank=column[m.pad])
    return spans


def hot_of(logp, lo: int, hi: int, pad: int) -> list[int]:
    if hi <= lo:
        return []
    avg = logp[lo:hi].exp().mean(dim=0)
    idx = (avg >= THR).nonzero(as_tuple=False).flatten().tolist()
    return [int(i) for i in idx if int(i) != pad]


def load_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    refs = load_json(REFS, {})
    native = load_json(NATIVE_PATH, {})
    done = set()
    if USER_PATH.exists():
        for line in USER_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["stem"])

    cards = htp.sidecars()
    by_sent: dict[str, list[dict]] = {}
    for card in cards:
        sent = (card.get("expected") or "").strip()
        if sent in refs and refs[sent]:
            by_sent.setdefault(sent, []).append(card)
    sents = sorted(by_sent)
    if limit:
        sents = sents[:limit]
    print(f"sentences {len(sents)}  takes already scored {len(done)}")

    m = wide.M()
    clock = time.monotonic()
    scored_takes = 0
    with USER_PATH.open("a", encoding="utf-8") as out:
        for si, sent in enumerate(sents, 1):
            words = refs[sent]
            symbols: list[str] = []
            groups: list[list[int]] = []
            for word, raws in words:
                if len(units(raws)) < _MIN_PHONES:
                    groups.append([])
                    continue
                start = len(symbols)
                symbols.extend(raws)
                groups.append(list(range(start, len(symbols))))
            if not symbols:
                continue
            if sent not in native:
                try:
                    raw, _times = htp.synth_voice(f"<speak>{sent}</speak>", htp.REF_VOICE)
                    pcm, rate = htp.pcm_from_wav(raw)
                    logp = forward(m, pcm, rate)
                    spans = land(m, logp, symbols)
                except Exception as exc:  # noqa: BLE001
                    print(f"  native skip {type(exc).__name__}")
                    native[sent] = {"ok": 0, "words": []}
                    NATIVE_PATH.write_text(
                        json.dumps(native), encoding="utf-8"
                    )
                    continue
                if spans is None:
                    native[sent] = {"ok": 0, "words": []}
                else:
                    packed = []
                    for group in groups:
                        if not group:
                            packed.append([])
                            continue
                        packed.append([
                            hot_of(logp, spans[k][0], spans[k][1], m.pad)
                            for k in group
                        ])
                    native[sent] = {"ok": 1, "words": packed}
                NATIVE_PATH.write_text(json.dumps(native), encoding="utf-8")
            pack = native[sent]
            if not pack.get("ok"):
                continue
            for card in by_sent[sent]:
                stem = card["stem"]
                if stem in done:
                    continue
                try:
                    pcm, rate = htp.pcm_of(m, stem)
                    logp = forward(m, pcm, rate)
                    spans = land(m, logp, symbols)
                except Exception as exc:  # noqa: BLE001
                    print(f"  take skip {type(exc).__name__}")
                    continue
                word_rows = []
                if spans is not None:
                    for wi, group in enumerate(groups):
                        if not group:
                            continue
                        native_hots = pack["words"][wi]
                        sounds = []
                        for j, k in enumerate(group):
                            hot = native_hots[j] if j < len(native_hots) else []
                            lo, hi = spans[k][0], spans[k][1]
                            avg = (
                                logp[lo:hi].exp().mean(dim=0)
                                if hi > lo
                                else None
                            )
                            top = max(hot, key=lambda i: float(avg[i]) if avg is not None else 0) if hot and avg is not None else -1
                            covered = bool(hot) and avg is not None and all(
                                float(avg[i]) >= THR for i in hot
                            )
                            top_p = float(avg[top]) if avg is not None and top >= 0 else 0.0
                            missed = [
                                i for i in hot
                                if avg is None or float(avg[i]) < THR
                            ]
                            sounds.append({
                                "hot_n": len(hot),
                                "covered": 1 if covered else 0,
                                "clear_miss": 1 if (
                                    len(hot) >= 2 and top_p >= CLEAR and missed
                                ) else 0,
                            })
                        word_rows.append(sounds)
                out.write(json.dumps({"stem": stem, "words": word_rows}) + "\n")
                out.flush()
                done.add(stem)
                scored_takes += 1
            print(
                f"  sentence {si}/{len(sents)}  new takes {scored_takes}"
                f"  {time.monotonic() - clock:.0f}s"
            )
    print("scored")
    report()
    return 0


def report() -> None:
    native = load_json(NATIVE_PATH, {})
    # A restarted run appends the same take again. The last copy wins.
    by_take: dict[str, dict] = {}
    if USER_PATH.exists():
        for line in USER_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                one = json.loads(line)
                by_take[one["stem"]] = one
    user_rows = list(by_take.values())
    wide_rows = load_json(WIDE, [])
    by_stem: dict[str, list[dict]] = {}
    for row in wide_rows:
        by_stem.setdefault(row["stem"], []).append(row)

    hot0 = hot1 = hot2 = 0
    covered = clear_miss = 0
    judged_sounds = 0
    good_scores: list[float] = []
    bad_scores: list[float] = []
    good_owner: list[float] = []
    bad_owner: list[float] = []
    joined = 0
    unjoined = 0
    empty_words = 0

    for take in user_rows:
        wide_words = by_stem.get(take["stem"]) or []
        mine = take["words"]
        if len(mine) != len(wide_words):
            unjoined += 1
        for i, sounds in enumerate(mine):
            matches = 0
            n = len(sounds)
            if n == 0:
                empty_words += 1
                continue
            for sound in sounds:
                judged_sounds += 1
                hn = int(sound["hot_n"])
                if hn == 0:
                    hot0 += 1
                elif hn == 1:
                    hot1 += 1
                else:
                    hot2 += 1
                if sound["covered"]:
                    covered += 1
                    matches += 1
                if sound["clear_miss"]:
                    clear_miss += 1
            if i >= len(wide_words):
                continue
            w = wide_words[i]
            said = n + max(0, int(w.get("extra_wide") or 0))
            score = matches / max(n, said)
            owner = float(w["sure"]) * n / max(n, said)
            joined += 1
            if w.get("bad"):
                bad_scores.append(score)
                bad_owner.append(owner)
            else:
                good_scores.append(score)
                good_owner.append(owner)

    def line_at(vals: list[float], keep: float = 0.90) -> float:
        if not vals:
            return 0.0
        ranked = sorted(vals)
        at = int(round((1.0 - keep) * (len(ranked) - 1)))
        return ranked[max(0, min(at, len(ranked) - 1))]

    print()
    print(f"takes {len(user_rows)}  sounds {judged_sounds}")
    print(f"native symbols at >={THR:.2f} (blank left out)")
    if judged_sounds:
        print(f"  none        {hot0:6d}  {hot0 / judged_sounds:.1%}")
        print(f"  one         {hot1:6d}  {hot1 / judged_sounds:.1%}")
        print(f"  two or more {hot2:6d}  {hot2 / judged_sounds:.1%}")
    print(f"sounds the reader covered {covered}")
    print(f"clear reading of the winner, still missing another  {clear_miss}")
    print(f"words joined to the old score {joined}  stems whose word count differed {unjoined}")
    if good_scores and bad_scores:
        for name, good, bad in (
            ("share30", good_scores, bad_scores),
            ("owner", good_owner, bad_owner),
        ):
            line = line_at(good)
            caught = sum(1 for v in bad if v < line)
            kept = sum(1 for v in good if v >= line)
            print(
                f"  {name:<8} line {line:.3f}"
                f"  kept {kept}/{len(good)} {kept / len(good):.0%}"
                f"  caught {caught}/{len(bad)} {caught / len(bad):.0%}"
            )
    print(f"native cache sentences {sum(1 for v in native.values() if v.get('ok'))}")


if __name__ == "__main__":
    raise SystemExit(main())
