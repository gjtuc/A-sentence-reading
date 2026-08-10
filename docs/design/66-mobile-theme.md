# 66 — Flutter theme (system / light / dark)

Modules: `theme_models.dart` · `theme_store.dart` · `theme_controller.dart` · `settings_screen.dart` · `app.dart`  
See: [33-mobile-flutter.md](33-mobile-flutter.md) · [07-typography-tokens.md](07-typography-tokens.md)

## What

User picks **시스템 / 밝음 / 어둠**. Choice survives app restart via SharedPreferences (`asr.theme.v1`).

| In | Out |
|----|-----|
| ThemeMode system/light/dark | TTS voice prefs (later) |
| Settings tab + Material light/dark ThemeData | Live Enable / IPS |
| Corrupt prefs → system default | Server round-trip |

## INVARIANT

- Theme never touches auth cookies / GCS / secrets
- Live Enable / IPS → Trading Gate (ASR out)

## EDGE

- null / empty / garbage prefs string → `system`
- unknown label → `system`
- setTheme during dispose → no-op safe
- MemoryThemeStore for tests (no plugin)

## Version

Web **0.2.82** · status `mobile_theme: true` · pubspec `0.2.82+1`

## Version pin

Web/mobile **0.2.96**.
