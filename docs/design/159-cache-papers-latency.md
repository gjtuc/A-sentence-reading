# 159 — cache/papers latency fix

**Version:** 0.3.88  
**Scope:** server list API + mobile library refresh UX.

## Problem

Authenticated `GET /api/cache/papers` took **30–50s** on Cloud Run while the mobile client timed out at **30s** (`listPapers`). Failed refresh cleared the paper list (`papers = []`).

## Root cause (confirmed)

Cloud Run HTTP latency logs for `Dart/3.12` clients showed 200 responses at 30–50s. `/api/status` stayed ~0.01s — not a global outage.

## Server fixes (0.3.88)

| Change | File | Why |
|--------|------|-----|
| Segment timing logs | `papers_gcs.py`, `app.py` | `cache_papers_timing` / `cache_papers_handler` in Cloud Logging |
| Lazy purge (≤1/h per instance) | `papers_gcs.py` `_maybe_purge_expired()` | `purge_expired_papers()` on every list could trigger many GCS deletes |
| Remote index TTL cache (45s, per uid) | `papers_gcs.py` `download_remote_index()` | Avoid repeated GCS index download on refresh |
| Invalidate index cache on upload | `upload_remote_index()` | Fresh list after ingest/delete |
| Single RTT GCS download | `gcs_sync.py` `download_bytes()` | Drop `blob.exists()` preflight |

### Log query

```bash
gcloud logging read \
  'textPayload:"cache_papers_timing"' --limit=10 \
  --project=peaceful-basis-503207-t4
```

Success: `total` < 5s on consecutive phone refreshes.

## Mobile fixes (0.3.88)

| Change | File |
|--------|------|
| `listPapers` timeout 30s → **60s** | `client.dart` |
| `TimeoutException` → Korean message | `library_controller.dart` |
| Keep `papers` on timeout | `library_controller.dart` |

## Verification

1. Deploy 0.3.88 Cloud Run
2. Phone library refresh 3× — no `TimeoutException`
3. Check `cache_papers_timing total=…` in logs
4. Install APK 0.3.88 on device
