# 91 — Device TTS unit lexicon E2E (Wh/L)

Modules: device APK 0.3.5 · live library · TTS  
받침: [90](90-tts-unit-lexicon.md) · [89](89-device-rich-display-e2e.md)

## 무엇인가

90에서 넣은 단위 발음(Wh L⁻¹ → watt hour per liter)을 **실기**에서 닫는다.

| 포함 | 미포함 |
|------|--------|
| APK 0.3.5 신규 설치 | 새 단위 사전 · UI |
| Google 창고 uid 보관 Li–S 논문 | iOS |
| `W h L⁻¹` 문장 TTS 청취(유저) | Live Enable / IPS |

## Product (locked this chip)

1. 계정: Google 창고 (`kimcha0809@gmail.com` 쪽 papers uid)  
2. 앱: **0.3.5 새로 설치**  
3. 확인: 유저가 재생 듣고 Wh/L이 수량 단위로 들리는지 판정

## Kill / rollback

- 이전 APK · design/90 revert

## Version

**0.3.5** (서버·앱 pin 유지 · 실기 확인 칩)

## Live Enable / IPS

이번 칩에서 불필요함.

## Device pin (E2E)

- 기기: SM-G986N · adb `R3CN20QX4BH`
- APK: **0.3.5** 신규 설치 · Google 창고 uid · Li–S 문장 21/23
- 라이브 status: `0.3.5`
- 유저 청취: `W h L⁻¹` → watt hour per liter (**OK**, 텅스텐 없음)

Do not paste magic URLs, session cookies, or invite codes into long-lived docs.
