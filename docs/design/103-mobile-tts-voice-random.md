# 103 — Mobile TTS voice + random difficulty

Modules: `tts_models.dart` · `tts_controller.dart` · `settings_screen.dart` · `shadowing_practice_screen.dart` · `reader_screen.dart`  
받침: [64](64-mobile-tts.md) · [96](96-tts-settings-tab.md) · 웹 `app.js` `ttsSettings` / `pickTtsPlaybackParams`

## 무엇인가

모바일 **설정 → TTS**에 웹과 같은 **모드(고정/랜덤 난이도)** 와 **목소리**를 둔다.  
읽기 TTS와 쉐도잉 **연습** 듣기 모두 같은 `TtsController` 설정을 쓴다.

| 포함 | 미포함 |
|------|--------|
| Settings: 모드 · 목소리 · 배속 (랜덤이면 목소리·배속 dim) | 웹 다이얼로그 「예시 듣기」 |
| prefs: mode · voice · rate | pitch UI |
| 재생마다 랜덤 locale/voice/rate (웹 가중치·대역 동일) | Live Enable / IPS |
| 연습 `_playTts` → 동일 pick | 서버 rate 캐시 변경 (여전히 1.0) |

## Product (locked)

1. Modes: `fixed` · `random_normal` · `random_hard` · `random_very_hard` (웹 라벨 동일).
2. Random: locale weights + rate bands mirror web; voice from curated list by locale prefix.
3. Fixed: selected voice + Settings rate (client `setPlaybackRate`).
4. Shadowing practice uses the same pick on each listen.

## Prefs

- `asr_tts_rate_v1` (기존)
- `asr_tts_mode_v1`
- `asr_tts_voice_v1`

## Kill / rollback

- Settings에 모드·목소리 UI 제거 · practice는 voice/rate 없이 synthesize

## Version

**0.3.17** · status + pubspec

## Device / pytest

- pure: mode normalize · pick fixed · pick random band clamp · locale weight
- dart sources: Settings labels · `pickTtsPlaybackParams` · practice wires `TtsController`
- 실기: 설정에서 목소리·랜덤 선택 후 읽기/연습 재생

Do not paste emails, cookies, or tokens into chat/PR.
