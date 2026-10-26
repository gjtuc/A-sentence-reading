# 463 — Web uploads and the cookie session

## Report

After design/462 the web queued files, but every upload stopped at 「로그인이 필요합니다.」 while the user was signed in.

## Cause

On the web the session is an HttpOnly cookie (design/405), so `SessionStore.readToken()` is empty. `createChunkedUpload`, the single-shot upload and `uploadPdf` checked that token before calling the server and threw 401 locally. Evidence: `upload_queue_pump_done` `fail_or_cancel` for all three files in the same second, `has_token: 0`. The multipart ingest also set its own `Cookie` header, which a browser refuses.

## Change

- The local token check runs off the web only (`_hasSessionToken`). On the web the server decides from its cookie and still returns 401 when the user is signed out.
- The multipart ingest takes its headers from `_headers()` like every other call.
