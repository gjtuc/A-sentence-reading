# 431 — PC launcher that hides the mouse, and the real web icon

## Mouse over an unfocused window

Measured with `.cache/cursor_probe/cursor_test.html`: Chrome sees the mouse
stop in an unfocused window, but does not repaint the cursor there until the
mouse moves. Hiding it, or a background-coloured or red cursor, all wait. So
the web app cannot hide the mouse over the window that was not clicked last.

## Launcher (`scripts/hide_mouse_in_app.ahk`, AutoHotkey v2)

- Opens the installed app (`chrome_proxy.exe --profile-directory="Profile 1"
  --app-id=...`) unless an app window is open.
- Every 100 ms: if the mouse has not moved for 3 s and the window under it is a
  Chrome/Edge window titled 「문장 읽기」, swap the system cursors for a blank
  one; restore the user's scheme on the first move and on exit.
- Quits 3 s after the last app window closes (30 s if none ever opened).

`scripts/make_app_launcher.ps1` makes the desktop shortcut 「문장 읽기」:
target AutoHotkey + the script, icon `scripts/app_icon.ico`, and the installed
app's AppUserModelID (`Chrome._crx_gmcbhmkeojidgcp.UserData.Profile1`, read from
Chrome's own shortcut). Pinned, the app windows group under it on the taskbar.
The web app cannot start a PC program, so the shortcut starts the app instead.

## Web icon

`mobile/web/icons/*` and `favicon.png` were still Flutter's default mark.
`scripts/make_app_icons.py` redraws the Android launcher mark (cream page, blue
sentence bar) at 192/512, favicon 32, and `scripts/app_icon.ico`. Mean pixel
difference from `mipmap-xxxhdpi/ic_launcher.png` at 192 px is about 3/255.
