# 369 — Ask the build, not the guess

Status locked

Two deploy guards were fixed. Both had the same defect: they answered a question
by **guessing from a name** instead of asking the thing that knows.

## Guard 1 — the parallel APK refusal (design/291)

`ship_release.sh` refuses a ship while an APK build is running, because a cloud
deploy kills the Gradle daemon out from under it. It decided this by scanning the
process list, and it was wrong twice in one day:

| Version | Matched | Caught by mistake | Result |
|---|---|---|---|
| original | `tasklist` image names `flutter\|dart` | the IDE Dart analysis server | every ship refused with the editor open |
| first fix | command line `GradleDaemon` | the idle daemon a finished build leaves behind for hours | every ship refused after any APK build |

A third name would have failed a third way, because no name in the process list
means "a build is running right now".

**Locked:** `build_release_apk.ps1` writes its own PID to
`.cache/apk_build.lock` before the build and removes it after.
`ship_release.sh` reads that PID and asks whether the process is alive. No
process-list pattern survives anywhere in the ship path — the test asserts that
`Win32_Process`, `GradleDaemon`, `GradleWrapperMain` and `tasklist` are all
absent from the code.

Three properties this buys:

- **A crashed build cannot block ships.** A dead PID is ignored, so cleanup is a
  courtesy rather than something correctness depends on.
- **A recycled PID cannot block ships.** The process name has to be
  `powershell` or `pwsh` too.
- **The build script uses the same lock**, so two APK builds still refuse each
  other.

## Guard 2 — the evidence floor (design/169g)

The floor freezes sensor names so a refactor cannot quietly delete live
observability. It checked this by asking whether the name appears in the file.

A name in a **comment** answered yes. So did a name in a **docstring**. That is
the exact loophole that lets someone hollow out a sensor — delete the emit, leave
the word behind — and still be told the floor is intact.

**Locked:** `code_only(text, suffix)` blanks line comments (`#`, `//`), block
comments (`/* */`, `<# #>`) and Python docstrings before any name is searched
for. Quotes are tracked, so a `#` or `//` inside a string such as a URL is not
mistaken for a comment, and line and column positions are preserved.

### What tightening it found

One frozen marker was satisfied only by a comment:
`ingest_lease_dual` in `src/sentence_reading/api/app.py`, where the line reads

```python
# design/284 ingest_lease_dual (kind emitted inside helper)
ilo.maybe_emit_lease_dual(job_id, job, hb_seq=hb_seq)
```

The sensor itself is fine — it is emitted in `ingest_lease_obs.py` and pinned in
that file's markers, and the `app.py` call site is pinned by
`maybe_emit_lease_dual`, which is real code. So the entry was watching nothing.
It was removed from the `app.py` list only. **Coverage did not shrink**; a
duplicate that could never fail was deleted.

Across every frozen kind and marker, that was the only one. Nothing lived solely
in a docstring.

## Known limit

Neither guard can prove an emit is ever **reached**. A name inside a branch that
never runs still passes, and no static check can fix that. The answer is live
evidence: `scripts/pull_evidence.py --kind <name>` shows whether a sensor has
actually fired. The floor is the cheap gate; live evidence is the real one.

## Not in this design

Re-pointing the practice sensors. `practice_skill_stt` names a **stage** — what
came back from analysing the recording — not the transcription service that
happens to fill it today. When design/370 replaces the transcript with the
native voice's own CTC run, the sensor keeps firing with real content, so the
floor needs no change for that work.
