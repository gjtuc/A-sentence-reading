"""design/381 - line a known sound sequence up against audio, and say how sure.

The scorer has been counting wrong sounds off the model's `argmax`, which throws
away the only number the model actually produces: a probability for every sound at
every frame. design/380 measured what that costs -- where two correct readings
disagree the model is 0.43 sure, against 0.90 where they agree, and a 0.35 guess
counts against the reader exactly as hard as a 0.97 certainty.

Using the probabilities needs one thing the scorer does not have: for each sound in
the reference, which stretch of the take it corresponds to. That is CTC forced
alignment. `torchaudio.functional.forced_align` does it, but torchaudio is not in
the server image and the alignment is a Viterbi pass over the CTC lattice, so it is
written out here instead. `tests/test_sound_align.py` checks it agrees with
torchaudio where torchaudio is installed.

Nothing here decides a boundary from sound (design/371): the sequence of sounds is
given, and all this does is find where each one landed.
"""
from __future__ import annotations

import math

# A token the model is not sure about anywhere is still a token; this is only the
# floor used when a span somehow ends up empty, which the lattice should prevent.
_FLOOR = 0.0


def _extended(tokens: list[int], blank: int) -> list[int]:
    """`[b, t0, b, t1, b, ...]` -- the CTC lattice's own alphabet."""
    out = [blank]
    for tid in tokens:
        out.append(tid)
        out.append(blank)
    return out


def align(
    logprobs: list[list[float]], tokens: list[int], *, blank: int
) -> list[tuple[int, int, float]] | None:
    """Where each token landed, and how sure the model was about it.

    `logprobs` is one row per frame and one column per sound, already log-softmaxed.
    Returns one `(first_frame, last_frame_exclusive, certainty)` per token, in the
    order given, or `None` when the sequence cannot fit the audio at all.

    Certainty is the mean probability over the frames the token was emitted on,
    which is what `torchaudio.functional.merge_tokens` reports.
    """
    frames = len(logprobs)
    if not tokens or frames == 0:
        return None
    ext = _extended(tokens, blank)
    wide = len(ext)
    # Every token needs a frame of its own, and a repeated token needs a blank
    # between the two, so a sequence longer than that cannot be aligned.
    need = len(tokens) + sum(
        1 for i in range(1, len(tokens)) if tokens[i] == tokens[i - 1]
    )
    if frames < need:
        return None

    neg = -math.inf
    # Viterbi over the lattice. `back[t][s]` is the lattice position we came from.
    best = [neg] * wide
    back: list[list[int]] = []
    best[0] = logprobs[0][ext[0]]
    if wide > 1:
        best[1] = logprobs[0][ext[1]]
    for t in range(1, frames):
        row = [neg] * wide
        came = [-1] * wide
        for s in range(wide):
            # Stay where we are.
            top, src = best[s], s
            if s >= 1 and best[s - 1] > top:
                top, src = best[s - 1], s - 1
            # Skip the blank between two different tokens.
            if (
                s >= 2
                and ext[s] != blank
                and ext[s] != ext[s - 2]
                and best[s - 2] > top
            ):
                top, src = best[s - 2], s - 2
            if top == neg:
                continue
            row[s] = top + logprobs[t][ext[s]]
            came[s] = src
        best = row
        back.append(came)

    # Finish on the last token or the blank after it.
    end = wide - 1
    if wide >= 2 and best[wide - 2] > best[end]:
        end = wide - 2
    if best[end] == neg:
        return None

    path = [0] * frames
    s = end
    for t in range(frames - 1, -1, -1):
        path[t] = s
        if t == 0:
            break
        s = back[t - 1][s]
        if s < 0:
            return None

    # Lattice position 2k+1 is token k; the even positions are blanks.
    spans: list[tuple[int, int, float]] = []
    for k in range(len(tokens)):
        pos = 2 * k + 1
        hits = [t for t in range(frames) if path[t] == pos]
        if not hits:
            spans.append((0, 0, _FLOOR))
            continue
        lo, hi = hits[0], hits[-1] + 1
        total = sum(math.exp(logprobs[t][tokens[k]]) for t in hits)
        spans.append((lo, hi, total / len(hits)))
    return spans


def certainty_by_group(
    logprobs: list[list[float]],
    groups: list[list[int]],
    *,
    blank: int,
) -> list[list[float]] | None:
    """Every sound's certainty, kept with the word it belongs to.

    One list per group, in the order given; an empty list for a group with no
    sound the model knows, which is the same thing `phoneOverlap` returning -1
    means today -- the word cannot be asked about.

    The average alone is not enough and the sounds are not recoverable from it.
    A word can average well while holding one sound the model gives almost no
    probability to, and that is the case the counting rule was blind to. So the
    reduction is left to the caller.

    design/371's rule holds: the words were cut by the reference builder from
    Google's own marks, and this only asks where each sound landed inside a cut
    that was already made.
    """
    flat: list[int] = []
    owner: list[int] = []
    for i, group in enumerate(groups):
        for tid in group:
            flat.append(tid)
            owner.append(i)
    if not flat:
        return None
    spans = align(logprobs, flat, blank=blank)
    if spans is None:
        return None
    out: list[list[float]] = [[] for _ in groups]
    for idx, (_lo, _hi, sure) in enumerate(spans):
        out[owner[idx]].append(sure)
    return out
