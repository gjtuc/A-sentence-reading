# 162 — 연습 전면 카메라 자기보기 + 보관/TTS UI polish (0.3.96)

## Product

| 항목 | 결정 |
|------|------|
| 보관 만료 | `(M/d 만료)` — 시간 없음 |
| 설정 TTS | 설명 2줄 + 모드 라벨 여백 |
| 연습 카메라 | 전면 미리보기만, 녹화·저장 없음 |
| 토글 | 세션 전용 — 진입 시 OFF, 켠 뒤 사용자가 끄거나 나갈 때까지 ON |
| 기본 | 카메라 OFF = 기존 연습 레이아웃 |

## Implementation

- `formatPaperMetaDate` — [`mobile/lib/api/paper_models.dart`](../../mobile/lib/api/paper_models.dart)
- TTS copy — [`mobile/lib/screens/settings_screen.dart`](../../mobile/lib/screens/settings_screen.dart)
- `PracticeMirrorPanel` + `camera: 0.10.6` (Camera2; Gradle 9 + camerax 0.11.x classpath issue) — [`mobile/lib/widgets/practice_mirror_panel.dart`](../../mobile/lib/widgets/practice_mirror_panel.dart)
  - **0.3.146:** preview uses `BoxFit.cover` + clip (no stretch into the short-wide panel)
- AppBar videocam toggle — [`mobile/lib/screens/shadowing_practice_screen.dart`](../../mobile/lib/screens/shadowing_practice_screen.dart)
- `CAMERA` permission — [`mobile/android/app/src/main/AndroidManifest.xml`](../../mobile/android/app/src/main/AndroidManifest.xml)

## Non-goals

- Video record/upload
- SharedPreferences for camera pref
- Server/API changes
