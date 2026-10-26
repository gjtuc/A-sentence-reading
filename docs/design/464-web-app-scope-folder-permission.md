# 464 — Installed web app scope and folder permission

## Report

The web asked 「허용 / 허용 안함」 every time a folder was opened, with no 「방문할 때마다 허용」 choice.

## Cause

Chrome keeps File System Access grants across sessions when the origin has extended permission. With no user choice stored, that is true only when an app installed with OS integration has the origin URL in scope (`OriginHasExtendedPermission` → `FindBestAppWithUrlInScope(origin.GetURL())`, i.e. `https://…run.app/`). Our manifest had no `scope`, so the scope defaulted to `/app/`. The root is not in it, so Chrome saw no installed app and asked again each session.

The three-way restore prompt did not show either. Chrome offers it only for dormant grants of a previous session, and a grant earlier in the same session turns them into shadow grants. That prompt cannot be relied on.

## Change

- `mobile/web/manifest.json`: `"scope": "/"`. `start_url` stays `.` and there is no `id`, so the app identity (`/app/`) is unchanged and the installed app updates in place.
- Chrome applies manifest updates on a later launch (it checks about once a day). Until then, or if the app was not installed with OS integration, reinstalling the app applies it at once.

## Test

`mobile/test/web_manifest_464_test.dart`.
