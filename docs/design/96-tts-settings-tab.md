# 96 — TTS defaults live in Settings

Modules: `mobile/lib/screens/settings_screen.dart` · `reader_screen.dart` · `tts_controller.dart`  
받침: [64](64-mobile-tts.md) · [68](68-mobile-shell.md)

## 무엇인가

읽기 탭 하단 **배속(speed)** 슬라이더를 **설정**으로 옮긴다.  
읽기의 **연습(쉐도잉)** 버튼은 유지. 배속은 prefs에 저장해 기본값으로 쓴다.

| 포함 | 미포함 |
|------|--------|
| Settings TTS 배속 UI · `asr_tts_rate_v1` persist | 보이스 피커 · 웹 설정 |
| Reader에서 speed row 제거 · 재생 버튼 유지 | Live Enable / IPS |

## Product (locked this chip)

1. Default TTS rate control is on Settings, not Reader.  
2. Shadowing practice entry on Reader stays.  
3. Rate persists across launches.

## Kill / rollback

- restore speed row on reader · drop Settings TTS block

## Version

**0.3.10** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
