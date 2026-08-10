# 68 — Mobile shell nav (auth gate · 3 tabs)

Modules: `home_shell.dart` · `login_screen.dart` · `settings_screen.dart` · `status_screen.dart`  
See: [33-mobile-flutter.md](33-mobile-flutter.md) · [61](61-mobile-email-auth.md) · [67](67-access-gate.md)

## Product

| Logged out | Logged in |
|------------|-----------|
| Login only (no bottom nav) | Tabs: **보관 · 읽기 · 설정** |

- Account identity + logout → **Settings → 계정**
- Server `/api/status` probe → **Settings → 서버** (admin only, nested page)
- No AppBar title chrome; SafeArea + small top pad
- User-facing copy must not mention Live Enable / IPS / Cloud Run

## Out of scope

| This chip | Later |
|-----------|--------|
| Shell / nav / settings placement | Keyboard notes → voice |
| | |
| Live Enable / IPS | Trading Gate only |

## Fail-closed

- No session → no library/reader tabs
- Non-admin → no Server tile (status dump hidden)
- Logout → shell returns to login; Settings clears access/mint state ([67](67-access-gate.md))

## Version

Web **0.2.98** · `mobile_shell_nav` · pubspec `0.2.98+1`
