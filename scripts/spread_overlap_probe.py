"""design/388 - the overlap of two spreads, measured on the 619 human takes.

Each reference sound is kept as its native spread: blank left out, the rest
scaled to 1. The reader's spread is read off the frames that sound landed on
and scaled the same way. The overlap is the sum of the smaller of the two,
symbol by symbol. This is the number stage two compares with the account line,
so the cold line has to be drawn from it, not from the design/375 overlap.

The scoring is the server's own `sound_score_of`. The native spread here comes
from the frames the reference symbols align to on the reference voice, which is
where the builder's argmax runs sit.

No paper text and no symbols are printed.

    python -u scripts/spread_overlap_probe.py
    python -u scripts/spread_overlap_probe.py --report
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm import hear_waveform as hw  # noqa: E402
from sentence_reading.llm.phone_match import _MIN_PHONES, split_phone_units  # noqa: E402
from sentence_reading.llm.sound_align import align  # noqa: E402

import human_takes_probe as htp  # noqa: E402
import timing_spread_probe as wide  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
NATIVE_PATH = ROOT / ".cache" / "spread388_native.json"
USER_PATH = ROOT / ".cache" / "spread388_user.jsonl"
WIDE = ROOT / ".cache" / "human_takes_wide.json"
REFS = ROOT / ".cache" / "human_refs_tokens.json"
OFFSET = -0.75
FLOOR = 0.45
RUNGS = (1, 10, 25, 40, 50)


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def forward(m, pcm, rate):
    values = m.fe(pcm, sampling_rate=rate, return_tensors="pt").input_values
    with m.torch.no_grad():
        logits = m.model(values).logits[0]
    return m.torch.log_softmax(logits, dim=-1)


def load_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def native_words(m, logp, words) -> list[list[str]] | None:
    """One spread string per sound of every word, or None if it cannot align."""
    ids = {s: i for i, s in m.inv.items()}
    flat: list[int] = []
    owner: list[int] = []
    for wi, (_word, raws) in enumerate(words):
        for s in raws:
            if s in ids:
                flat.append(ids[s])
                owner.append(wi)
    if not flat:
        return None
    wanted = sorted(set(flat) | {m.pad})
    column = {tid: i for i, tid in enumerate(wanted)}
    spans = align(
        logp[:, wanted].tolist(), [column[t] for t in flat], blank=column[m.pad]
    )
    if spans is None:
        return None
    out: list[list[str]] = [[] for _ in words]
    for k, wi in enumerate(owner):
        lo, hi = spans[k][0], spans[k][1]
        if hi <= lo:
            out[wi].append("")
            continue
        avg = logp[lo:hi].exp().mean(dim=0)
        spread = hw.native_spread({
            name: float(avg[i]) for i, name in m.inv.items()
            if i != m.pad and name
        })
        out[wi].append(hw.spread_text(spread))
    return out


def main() -> int:
    if "--report" in sys.argv:
        report()
        return 0
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
    by_sent: dict[str, list[dict]] = {}
    for card in htp.sidecars():
        sent = (card.get("expected") or "").strip()
        if sent in refs and refs[sent]:
            by_sent.setdefault(sent, []).append(card)
    sents = sorted(by_sent)
    if limit:
        sents = sents[:limit]
    print(f"sentences {len(sents)}  takes already scored {len(done)}")
    m = wide.M()
    clock = time.monotonic()
    scored = 0
    with USER_PATH.open("a", encoding="utf-8") as out:
        for si, sent in enumerate(sents, 1):
            words = [(w, [s for s in raws]) for w, raws in refs[sent]]
            if sent not in native:
                try:
                    raw, _t = htp.synth_voice(f"<speak>{sent}</speak>", htp.REF_VOICE)
                    pcm, rate = htp.pcm_from_wav(raw)
                    packed = native_words(m, forward(m, pcm, rate), words)
                except Exception as exc:  # noqa: BLE001
                    print(f"  native skip {type(exc).__name__}")
                    packed = None
                native[sent] = {"ok": 1 if packed else 0, "words": packed or []}
                NATIVE_PATH.write_text(json.dumps(native), encoding="utf-8")
            pack = native[sent]
            if not pack.get("ok"):
                continue
            groups = [list(raws) for _w, raws in words]
            shares = [
                [hw.parse_spread(one) for one in slots] for slots in pack["words"]
            ]
            askable = [len(units(raws)) >= _MIN_PHONES for _w, raws in words]
            for card in by_sent[sent]:
                stem = card["stem"]
                if stem in done:
                    continue
                try:
                    pcm, rate = htp.pcm_of(m, stem)
                    got = hw.sound_score_of(forward(m, pcm, rate), groups, shares)
                except Exception as exc:  # noqa: BLE001
                    print(f"  take skip {type(exc).__name__}")
                    continue
                rows = []
                for wi, one in enumerate(got or []):
                    if not askable[wi] or not one:
                        continue
                    rows.append({
                        "n": int(one["n"]),
                        "said": int(one["said"]),
                        "each": [round(v, 4) for v in one["each"]],
                        "loose": [round(v, 4) for v in one["loose"]],
                        "quiet": one["quiet"],
                        "top": [
                            [[round(a, 3), round(b, 3)] for a, b in sound]
                            for sound in one["top"]
                        ],
                    })
                out.write(json.dumps({
                    "stem": stem, "tier": card.get("skill_tier"),
                    "ok": 1 if got else 0, "words": rows,
                }) + "\n")
                out.flush()
                done.add(stem)
                scored += 1
            print(
                f"  sentence {si}/{len(sents)}  new takes {scored}"
                f"  {time.monotonic() - clock:.0f}s"
            )
    report()
    return 0


def line_of(vals: list[float]) -> tuple[float, float, float]:
    mean = stat.fmean(vals)
    spread = stat.pstdev(vals)
    return mean, spread, max(mean + OFFSET * spread, FLOOR)


def sound_passes(overlap: float, top, bar: float, line: float) -> bool:
    need = [b for a, b in top if a >= bar - 1e-9]
    if need and all(b >= bar - 1e-9 for b in need):
        return True
    return overlap >= line


def handover(*, word_overlaps: list[list[float]], line: float, per_word: float) -> None:
    """Where an account's own line sits when it warms up, the phone's own update.

    The words are shuffled 400 ways and fed sound by sound, with the warm-up and
    the weight both counted in sounds at this many sounds per word, so they are
    the same forty words and the same 1% per word as before.
    """
    import math
    import random

    warm = round(40 * per_word)
    weight = 0.01 / per_word
    rng = random.Random(388)
    lines = []
    for _ in range(400):
        order = list(word_overlaps)
        rng.shuffle(order)
        avg = varp = 0.0
        n = 0
        for word in order:
            for score in word:
                n += 1
                if n == 1:
                    avg, varp = score, 0.0
                    continue
                w = max(weight, 1.0 / n)
                gap = score - avg
                avg += w * gap
                varp = (1 - w) * (varp + w * gap * gap)
            if n >= warm:
                break
        lines.append(max(avg + OFFSET * math.sqrt(max(varp, 0)), FLOOR))
    lines.sort()
    floored = sum(1 for v in lines if v <= FLOOR + 1e-9)
    print(
        f"  warm-up {warm} sounds (40 words)  weight {weight:.5f}"
        f"  own line at warm-up: median {lines[200]:.3f}"
        f"  10-90% {lines[40]:.3f}-{lines[360]:.3f}"
        f"  at the floor {floored}/400  cold {line:.3f}"
    )


def report() -> None:
    by_take: dict[str, dict] = {}
    if USER_PATH.exists():
        for line in USER_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                one = json.loads(line)
                by_take[one["stem"]] = one
    labels: dict[str, list[dict]] = {}
    for row in load_json(WIDE, []):
        labels.setdefault(row["stem"], []).append(row)

    sounds: list[float] = []
    loose: list[float] = []
    word_means: list[float] = []
    quiet = 0
    per_word_n: list[int] = []
    top_none = top_one = top_more = 0
    joined: list[tuple[dict, bool]] = []
    unjoined = 0
    for take in by_take.values():
        words = take["words"]
        lab = labels.get(take["stem"]) or []
        if len(lab) != len(words):
            unjoined += 1
        for i, w in enumerate(words):
            sounds.extend(w["each"])
            loose.extend(w["loose"])
            quiet += sum(w["quiet"])
            per_word_n.append(w["n"])
            word_means.append(stat.fmean(w["each"]))
            for sound in w["top"]:
                at = sum(1 for a, _b in sound if a >= 0.21 - 1e-9)
                if at == 0:
                    top_none += 1
                elif at == 1:
                    top_one += 1
                else:
                    top_more += 1
            if i < len(lab) and len(lab) == len(words):
                joined.append((w, bool(lab[i].get("bad"))))

    print()
    print(f"takes {len(by_take)}  words {len(per_word_n)}  sounds {len(sounds)}")
    if not sounds:
        return
    mean, spread, line = line_of(sounds)
    print("per-sound overlap (stage two's number), no labels")
    print(f"  mean {mean:.3f}  spread {spread:.3f}  mean - 0.75 x spread = {mean + OFFSET * spread:.3f}")
    lm, ls, _ll = line_of(loose)
    print(f"  without the silence guard: mean {lm:.3f}  spread {ls:.3f}  line {lm + OFFSET * ls:.3f}")
    print(f"  sounds the model heard as only blank {quiet}  {quiet / len(sounds):.1%}")
    wm, ws, _wl = line_of(word_means)
    print(f"per-word mean overlap: mean {wm:.3f}  spread {ws:.3f}  line {wm + OFFSET * ws:.3f}")
    print(f"judged sounds per word {stat.fmean(per_word_n):.2f}")
    total = top_none + top_one + top_more
    print(
        f"native symbols at >= 21%: none {top_none / total:.1%}"
        f"  one {top_one / total:.1%}  two or more {top_more / total:.1%}"
    )
    print(f"words joined to labels {len(joined)}  takes whose word count differed {unjoined}")
    good = [w for w, bad in joined if not bad]
    bad = [w for w, bad in joined if bad]
    if not good or not bad:
        return
    for rung in RUNGS:
        bar = (20 + rung) / 100.0
        def score(w):
            hits = sum(
                1 for ov, top in zip(w["each"], w["top"])
                if sound_passes(ov, top, bar, line)
            )
            return hits / max(w["n"], w["said"])
        kept = sum(1 for w in good if score(w) >= line)
        caught = sum(1 for w in bad if score(w) < line)
        stage1 = sum(
            1 for w in good for ov, top in zip(w["each"], w["top"])
            if [b for a, b in top if a >= bar - 1e-9]
            and all(b >= bar - 1e-9 for a, b in top if a >= bar - 1e-9)
        )
        good_sounds = sum(len(w["each"]) for w in good)
        print(
            f"  rung {rung:2d} bar {bar:.2f} line {line:.3f}"
            f"  kept {kept}/{len(good)} {kept / len(good):.0%}"
            f"  caught {caught}/{len(bad)} {caught / len(bad):.0%}"
            f"  good sounds passed at stage one {stage1 / good_sounds:.0%}"
        )
    handover(word_overlaps=[w["each"] for w, _bad in joined], line=line,
             per_word=stat.fmean(per_word_n))
    gq = sum(sum(w["quiet"]) for w in good)
    gs = sum(len(w["quiet"]) for w in good)
    bq = sum(sum(w["quiet"]) for w in bad)
    bs = sum(len(w["quiet"]) for w in bad)
    print(f"  heard-as-blank sounds: right words {gq}/{gs} {gq / gs:.1%}  wrong words {bq}/{bs} {bq / bs:.1%}")


if __name__ == "__main__":
    raise SystemExit(main())
