# 90 — TTS unit lexicon (Wh/L · SI energy)

Modules: `llm/tts_speak.py` · tests  
받침: [15](15-tts-and-gestures.md) · [88](88-rich-display-tts-polish.md)

## 무엇인가

`2800 W h L⁻¹`가 “tungsten H L minus one”처럼 읽히는 구멍.  
논문에 흔한 **에너지·전기·농도·분광 단위**를 “watt hour per liter”처럼 말하게 한다.

| 포함 | 미포함 |
|------|--------|
| 복합 단위 사전 (Wh L⁻¹, mAh g⁻¹, kJ mol⁻¹, cm⁻¹ …) | MathML · 새 UI |
| 단위 문맥에서 `W`≠텅스텐 등 원소 충돌 완화 | 모든 IUPAC 단위 |
| pytest | Live Enable / IPS |

## Product (locked this chip)

User: TTS must speak units as quantities (e.g. watt hour per liter), not element names / letter spelling.

## Kill / rollback

- revert `tts_speak.py` unit block · prior revision

## Version

**0.3.5** · status + pubspec pin

## Live Enable / IPS

이번 칩에서 불필요함.
