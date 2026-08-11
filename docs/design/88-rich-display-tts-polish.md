# 88 — Rich display (web+app) + TTS polish + device E2E

Modules: `mobile/` reader · `static/app.js` · `llm/tts_speak.py` · `llm/richtext.py`  
받침: [13](13-rich-text-two-pass.md) · [15](15-tts-and-gestures.md) · [63](63-mobile-reader.md) · [64](64-mobile-tts.md)

## 무엇인가

본문에 `<sub>`가 **글자로** 보이거나, TTS가 화학식·단위를 어색하게 읽는 구멍을 줄인다.  
웹·앱 **표시** + 서버 **TTS 손질** + 폰에서 논문 열어 확인.

| 포함 | 미포함 |
|------|--------|
| 앱: 허용 태그(`sub`/`sup`/`i`/`em`) Text.rich 렌더 | MathML · 다줄 반응식 |
| 웹: 표시 전 클라 sanitize · KO 쪽 raw 태그 방지 | 새 ingest/debone 모델 |
| TTS: 단위·첨자·기호 발음 보강 (`spoken_text_for_tts`) | Live Enable / IPS · iOS |

## Product (locked this chip)

1. **웹 + 앱** 같이  
2. **화면 표시 + TTS 손질**  
3. **폰에서 논문 열어 첨자 E2E**

## Kill / rollback

- 앱: plain `Text` 폴백 · 이전 APK  
- TTS: `spoken_text_for_tts` revert · 또는 합성 전 plain strip만  
- 웹: `innerHTML` 직전 sanitize 제거(기존 서버 sanitize만)

## Version

**0.3.4** · pubspec `0.3.4+1` (서버 status 버전 동일 pin)

## Live Enable / IPS

이번 칩에서 불필요함.

Do not paste session cookies, magic URLs, or invite codes into long-lived docs.
