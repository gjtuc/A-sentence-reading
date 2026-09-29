"""Which quiet does the tiling pick, and is it the one between the words?

The tiling gave `light`'s final `t` to `passes` and `without`'s final `t` to
`loss`. If a word-final plosive holds a wider silence than the space between the
words, then cutting at the widest quiet cuts inside the word, and "cut at the
quiet" is not the fact it looked like.
"""
from __future__ import annotations

import pathlib
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from mark_boundary_probe import synth  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

SENT = "The light passes through the water without loss."


def nm(u: str) -> str:
    return "-".join(unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in u)


def main() -> int:
    m = wide.M()
    ssml, words = ssml_with_marks(SENT)
    raw, times = synth(ssml, 1.0)
    pcm, rate = pcm_from_wav(raw)
    heard = m.run(pcm, rate)
    t0 = [m.s(s["f0"], rate) for s in heard]
    t1 = [m.s(s["f1"], rate) for s in heard]

    out = ["symbol run with the quiet before each sound"]
    for k, s in enumerate(heard):
        gap = 0.0 if k == 0 else max(0.0, t0[k] - t1[k - 1])
        out.append(f"  {k:>2} {nm(s['sym']):<10} start {t0[k] * 1000:7.0f}ms "
                   f"end {t1[k] * 1000:7.0f}ms  quiet before {gap * 1000:6.0f}ms")
    out.append("")
    out.append("word marks, and the quiets the tiling could choose from")
    for i, word in enumerate(words):
        mark = times[f"w{i}"]
        out.append(f"  {word:<10} mark {mark * 1000:7.0f}ms")
        for k in range(len(heard)):
            mid = t0[0] if k == 0 else (t1[k - 1] + t0[k]) / 2
            if not (mark - 0.060 <= mid <= mark + 0.100):
                continue
            gap = 0.0 if k == 0 else max(0.0, t0[k] - t1[k - 1])
            out.append(f"       candidate before {nm(heard[k]['sym']):<10} "
                       f"middle {mid * 1000:7.0f}ms  quiet {gap * 1000:6.0f}ms"
                       f"   (mark{(mid - mark) * 1000:+.0f}ms)")
    pathlib.Path(".cache/quiet_dump.txt").write_text(
        "\n".join(out), encoding="utf-8"
    )
    print(f"wrote .cache/quiet_dump.txt  ({len(heard)} sounds, {len(words)} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
