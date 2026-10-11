# 395 — The API scales to zero

**Version:** 0.3.434 · Status: **locked**
Amends [173](173-capacity-isolation-roadmap.md) (`--min-instances` 1 kept) and the
[378](378-warm-the-paper-not-the-reader.md) note that one instance always stays up.

## Why

Measured over 30 days before this change (Cloud Monitoring, `asr-sentence-reading`):

| | |
|---|---|
| Billable instance time | 729 h (one instance all month) |
| Hours with any request | 340 of 720 |
| Memory peak (p99 of utilization) | 62.6% of 8 Gi, 5.0 Gi |
| Container start | 4–7 s |
| Phoneme model load (`stt_warm` `warm_ms`) | 21–23 s |

`--min-instances 1` with CPU always allocated paid 2 vCPU and 8 Gi for every idle hour.
The background loops (sweeper 60 s, TTL purges 1 h, evidence rotate) are light; they
cost nothing by themselves, only through the instance they keep busy.

The worker service had 0 requests in 7 days (the API runs ingest inline) and already
scales to zero. It is left as is.

## Locked

1. `deploy_cloud_run.sh` defaults `--min-instances` to **0**. `ASR_MIN_INSTANCES=1`
   brings the warm instance back.
2. `deploy_cloud_run_pair.sh` defaults API memory to **6 Gi**. `ASR_API_MEMORY`
   overrides.
3. On Cloud Run API instances the model loads in a background thread as the app
   starts (`_hear_preload_on_boot`, thread `hear-preload`), so the 21 s load does not
   land on the first take. `ASR_HEAR_PRELOAD=0|1` overrides. Not on the worker, not in
   local tests.
4. The load is logged as `practice_skill_stt` route `boot_warm` with `warm_ms`.
5. CPU stays always allocated. Ingest and the sound-reference warm run after the
   response returns; request-based CPU would freeze them.

6. Two paths deploy the API on every push: the local ship and GitHub CD
   (`vars.ASR_CAPACITY_PROFILE` = `turn2-scale-to-zero`). The last one to finish
   wins. The CD profile had `ASR_INGEST_INLINE=0`, which moves ingest and the
   sound-reference warm to the 2 Gi worker, too small for the phoneme model. 0.3.434
   went live that way through CD. The profile now says `1`, like the local ship
   (0.3.435).

## Costs that remain

- An idle instance lives up to about 15 minutes after the last request.
- The first request after idle waits for a container start (4–7 s).
- Closing the app during a long sound-reference warm can let the instance stop; the
  warm resumes when the paper is opened again (design/378).

## Check after deploy

- `minScale` absent or 0 and memory `6Gi` on the live revision.
- `boot_warm` rows with `warm_ok` 1.
- No `memory limit exceeded` in Cloud Run logs during paper analysis.

## Tests

`tests/test_scale_to_zero_395.py`.
