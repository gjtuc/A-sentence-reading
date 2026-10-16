# 405 — The server hosts the web app at /app/, and the web app logs in (step 2 of the web version)

## Goal of this step

Open `https://<server>/app/` in a browser, ask for a login link by email, open the
link, and come back to `/app/` logged in. The old server page at `/` is untouched.
Library, reading, upload, voice and shadowing are later steps (403 lists them).

## What was in the way

- The login gate redirected every unknown page to `/`, so `/app/` could not load.
- The web app called the fixed Cloud Run address, not the page it was loaded from.
  Served from a second address that is a cross-origin call, and the session cookie
  set by the link is not sent.
- The app put the session token in a `Cookie` header itself. A browser refuses to let
  a page set that header; the browser sends its own cookie on same-origin calls.
- The magic link request always said `client: android`, so the emailed link opened the
  Android deep link, not a web page.

## What changed

- `is_login_public_path` opens `/app` and `/app/*`. Only the app shell is public; every
  `/api/*` call it makes still needs the session.
- `app.py` mounts `src/sentence_reading/web_app` at `/app` when its `index.html` exists.
  Files are sent with `Cache-Control: no-cache` (a new deploy is picked up on the next
  load) and `X-Robots-Tag: noindex, nofollow` (design/396: crawlers wake the server).
- Magic link request with `client: web_app` adds `&land=app` to the emailed link.
  `/api/auth/email/magic/open?...&land=app` sets the same `asr_session` cookie as the
  old web page and redirects to `/app/?auth=logged_in`; errors go to
  `/app/?auth_error=...`. Without `land` the old `/` targets stay.
- Flutter: on the web `effectiveBaseUrl` is `Uri.base.origin` (a test override still
  wins), `_headers` skips the `Cookie` header, and both magic requests send
  `kMagicLinkClient` (`web_app` on the web, `android` elsewhere). The app already asks
  `/api/auth/status` at start, which reads the browser cookie.
- Shipping: `pyproject.toml` package-data includes `web_app/**/*`, and `.gcloudignore`
  re-includes `src/sentence_reading/web_app/**` after its `*.png` rule (the icons).

## Build and check

- `scripts/build_web_app.py` runs `flutter build web --release --base-href /app/` and
  replaces `src/sentence_reading/web_app` with the build, minus `canvaskit/` (the loader
  fetches CanvasKit from Google's CDN) and `.last_build_id`. It fails when the build was
  not made for `/app/` or `version.json` differs from `pubspec.yaml`.
- `scripts/web_probe.py --app` serves `web_app` at `/app/` and forwards `/api/*` to the
  live server, so the page and its API share one origin as they do in production.
  CORS errors are therefore real errors now.
- `click\03_web_build.bat` runs both and fails on any uncaught error, other error or
  CORS line. `click\02_ship_and_install.bat` refuses to deploy when
  `web_app/version.json` is not the app version (run 03 and commit first).

## Order

1. Commit the code (this change).
2. Double-click `click\03_web_build.bat`. Commit `src/sentence_reading/web_app`.
3. Double-click `click\02_ship_and_install.bat`.
4. Open `/app/` on the live server and log in with an email link.

## Tests

`tests/test_design_405_web_app_hosting.py`
