# 89 — Device rich-display E2E (stored chem paper)

Modules: device APK 0.3.4 · live library · TTS  
받침: [88](88-rich-display-tts-polish.md) · [63](63-mobile-reader.md) · [64](64-mobile-tts.md)

## 무엇인가

88에서 넣은 앱 rich 표시·TTS 손질을, **지금 쓰는 이메일 계정의 보관 논문**으로 실기에서 닫는다.

| 포함 | 미포함 |
|------|--------|
| 보관함에서 첨자·특수문자·화학식 있는 논문 열기 | 새 ingest / MathML |
| 문장 UI에 raw `<sub>` 없음 | iOS |
| 같은 문장 TTS 청취 | Live Enable / IPS |

## Product (locked this chip)

1. 계정: **지금 쓰는 이메일**  
2. 논문: **이미 보관된 것** 중 첨자·특수문자·화학식 있는 것  
3. 확인: **표시 + TTS 전부**

## Kill / rollback

- 이전 APK · design/88 revert

## Version

**0.3.4** (서버·앱 pin 유지 · 실기 확인 칩)

## Live Enable / IPS

이번 칩에서 불필요함.

## Device pin (E2E)

- Account on device: email shown in Settings matches current mailbox (`kimcha…@gmail.com`); papers loaded from Google-linked warehouse uid (email-magic uid alone had 0 papers)
- Opened stored paper: *Unique behaviour of nonsolvents… lithium–sulphur batteries* (23 sentences)
- Sentence ~21: volumetric energy density / `W h L⁻¹` — accessibility tree shows `-1` as separate script runes, **no** raw `<sub>`/`<sup>` strings (`RAW_FINAL=false`)
- TTS: `play TTS` → `stop TTS` (playing) on that sentence
- Specials: en-dash in title `lithium–sulphur` visible in reader header

Do not paste magic URLs, session cookies, or invite codes into long-lived docs.
