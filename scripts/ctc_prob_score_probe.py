"""Score a word by how sure the model is, instead of counting wrong sounds.

Today a word's score is 1 - wrong / longer, counted off the hard symbol
sequence left after argmax. That throws away what the model actually produced:
a probability for every sound at every 20 ms frame. Under the counting rule a
genuinely wrong sound and a correct sound the model was merely unsure about
cost exactly the same, so a long word bleeds points to ordinary voice noise
until the correct and the wrong reading meet. That is design/371 section 7.

This asks the model the direct question instead. Line the reference sounds up
against the take, then average how sure the model was about each one. A
confident correct sound scores near 1.0, a wrong one near 0.0, and an average
does not care how many sounds the word has.

Lining a fixed sequence up against frames is CTC's own forward pass, so there
is nothing here to invent and nothing to tune.
"""

from __future__ import annotations

import collections
import json
import pathlib
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    best_window_overlap,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402
from two_voices_probe import cut_own, ssml_broken  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

SHOW = [
    ("The light passes through the water without loss.", "loss", "lost"),
    ("The single cell performance was stable for one hundred hours.",
     "stable", "table"),
]

BREAK = 100
PAD = 25


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def logprobs(m, pcm, rate):
    """The whole probability sheet: one row per 20 ms frame, one column per sound."""
    values = m.fe(pcm, sampling_rate=rate, return_tensors="pt").input_values
    with m.torch.no_grad():
        logits = m.model(values).logits
    return m.torch.log_softmax(logits, dim=-1)[0]


def sure_per_word(m, sheet, refs: list[list[str]]):
    """Average certainty per word, plus the frames the word landed on."""
    import torchaudio.functional as F

    ids = {s: i for i, s in m.inv.items()}
    flat: list[int] = []
    owner: list[int] = []
    for i, syms in enumerate(refs):
        for s in syms:
            if s in ids:
                flat.append(ids[s])
                owner.append(i)
    blank = [None] * len(refs)
    if not flat or len(flat) >= sheet.shape[0]:
        return blank
    targets = m.torch.tensor([flat], dtype=m.torch.int32)
    aligned, score = F.forced_align(sheet.unsqueeze(0), targets, blank=m.pad)
    spans = F.merge_tokens(aligned[0], score[0].exp(), blank=m.pad)
    if len(spans) != len(flat):
        return blank
    bag: list[list[float]] = [[] for _ in refs]
    edge: list[list[int]] = [[] for _ in refs]
    for k, span in enumerate(spans):
        bag[owner[k]].append(float(span.score))
        edge[owner[k]] += [int(span.start), int(span.end)]
    return [
        (sum(b) / len(b), min(e), max(e)) if b else None
        for b, e in zip(bag, edge)
    ]


def nm(sym: str) -> str:
    """A console-safe name for a sound. The Windows console cannot print IPA."""
    import unicodedata

    return "-".join(
        unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in sym
    )


def _per_sound(m, sheet, refs, which: int):
    """The certainty the alignment gave each single sound of one word."""
    import torchaudio.functional as F

    ids = {s: i for i, s in m.inv.items()}
    flat, owner = [], []
    for i, syms in enumerate(refs):
        for s in syms:
            if s in ids:
                flat.append(ids[s])
                owner.append(i)
    targets = m.torch.tensor([flat], dtype=m.torch.int32)
    aligned, score = F.forced_align(sheet.unsqueeze(0), targets, blank=m.pad)
    spans = F.merge_tokens(aligned[0], score[0].exp(), blank=m.pad)
    return [
        (m.inv[flat[k]], float(spans[k].score))
        for k in range(len(flat))
        if owner[k] == which
    ]


def show(m, pick):
    """Walk one word sound by sound, so the numbers can be read by hand."""
    for sent, target, wrong in pick:
        ssml, words = ssml_broken(sent, BREAK)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        clean = cut_own(
            m, m.run(pcm, rate), words, times, rate, PAD, len(pcm) / rate
        )
        refs = [list(syms) for _w, syms in clean]
        said = sent.replace(target, wrong, 1)
        raw2, _t = synth_voice(f"<speak>{said}</speak>", READ_VOICE)
        pcm2, rate2 = pcm_from_wav(raw2)
        sheet = logprobs(m, pcm2, rate2)
        heard = m.run(pcm2, rate2)
        sure = sure_per_word(m, sheet, refs)
        run = units(s["sym"] for s in heard)

        i = [w.lower() for w, _s in clean].index(target.lower())
        ref = units(refs[i])
        cert, f0, f1 = sure[i]
        here = [s for s in heard if f0 <= (s["f0"] + s["f1"]) / 2 < f1]
        over = max(0, len(here) - len(ref))
        print(f"\n{target} read as {wrong}   in: {sent}")
        print(f"  reference sounds ({len(ref)}): {' '.join(nm(u) for u in ref)}")
        print(f"  take has there   ({len(here)}): "
              f"{' '.join(nm(s['sym']) for s in here)}")
        print(f"  frames {f0}..{f1} = {m.s(f0, rate2):.2f}s..{m.s(f1, rate2):.2f}s")
        print("  sure of each reference sound, in order:")
        for k, one in enumerate(_per_sound(m, sheet, refs, i)):
            print(f"    {k + 1:>2}. {nm(one[0]):<14} {one[1]:.3f}")
        print(f"  average sure         {cert:.3f}")
        print(f"  said more than asked {over} -> minus {over / len(ref):.3f}")
        print(f"  new score            {cert - over / len(ref):.3f}")
        print(f"  today score          {best_window_overlap(ref, run):.3f}")
    return 0


def keep_line(correct: list[float], keep: float = 0.90) -> float:
    """The pass line that lets through `keep` of the correct readings."""
    if not correct:
        return 0.0
    ranked = sorted(correct)
    at = int(round((1.0 - keep) * (len(ranked) - 1)))
    return ranked[max(0, min(at, len(ranked) - 1))]


def main() -> int:
    m = wide.M()
    if "--show" in sys.argv:
        return show(m, SHOW)
    print(f"blank id {m.pad}, vocab {len(m.inv)}")

    rows = []
    for sent, pairs in SWAPS.items():
        ssml, words = ssml_broken(sent, BREAK)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        clean = cut_own(
            m, m.run(pcm, rate), words, times, rate, PAD, len(pcm) / rate
        )
        refs = [list(syms) for _w, syms in clean]
        names = [w for w, _s in clean]

        for target, wrong in pairs:
            said = sent.replace(target, wrong, 1)
            raw2, _t = synth_voice(f"<speak>{said}</speak>", READ_VOICE)
            pcm2, rate2 = pcm_from_wav(raw2)
            sheet = logprobs(m, pcm2, rate2)
            heard = m.run(pcm2, rate2)
            run = units(s["sym"] for s in heard)
            sure = sure_per_word(m, sheet, refs)
            for i, name in enumerate(names):
                ref = units(refs[i])
                if len(ref) < _MIN_PHONES or sure[i] is None:
                    continue
                cert, f0, f1 = sure[i]
                # What the take actually has where the word landed. Sounds over
                # and above the reference are the "said more than asked" term.
                said = units(
                    s["sym"] for s in heard
                    if f0 <= (s["f0"] + s["f1"]) / 2 < f1
                )
                extra = max(0, len(said) - len(ref))
                rows.append(
                    {
                        "sent": sent,
                        "word": name,
                        "n": len(ref),
                        "bad": 1 if name.lower() == target.lower() else 0,
                        "overlap": best_window_overlap(ref, run),
                        "sure": cert,
                        "full": cert - extra / len(ref),
                        "extra": extra,
                    }
                )
        print(f"read {sent[:44]}")

    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]
    print(f"\n{len(rows)} judged words: {len(good)} read right, {len(bad)} read wrong")

    report = {"rows": rows, "ways": {}}
    for way in ("overlap", "sure", "full"):
        line = keep_line([r[way] for r in good])
        caught = sum(1 for r in bad if r[way] < line)
        kept = sum(1 for r in good if r[way] >= line)
        print(f"\n{way}: pass line {line:.3f} (set to keep 90% of right readings)")
        print(f"  caught {caught}/{len(bad)} {caught / max(1, len(bad)):.0%}"
              f"   kept {kept}/{len(good)} {kept / max(1, len(good)):.0%}")
        print("  sounds  right  wrong    gap   caught")
        by_n: dict[int, dict[str, list[float]]] = collections.defaultdict(
            lambda: {"g": [], "b": []}
        )
        for r in rows:
            by_n[r["n"]]["b" if r["bad"] else "g"].append(r[way])
        cells = {}
        for n in sorted(by_n):
            g, b = by_n[n]["g"], by_n[n]["b"]
            if not b:
                continue
            gm = stat.mean(g) if g else float("nan")
            bm = stat.mean(b)
            hit = sum(1 for v in b if v < line)
            print(f"  {n:>6}  {gm:.3f}  {bm:.3f}  {gm - bm:+.3f}   {hit}/{len(b)}")
            cells[n] = {
                "right": gm, "wrong": bm, "gap": gm - bm,
                "caught": hit, "targets": len(b), "n_right": len(g),
            }
        report["ways"][way] = {
            "line": line, "caught": caught, "targets": len(bad),
            "kept": kept, "keepable": len(good), "by_length": cells,
        }

    pathlib.Path(".cache/ctc_prob_score.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\nwrote .cache/ctc_prob_score.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
