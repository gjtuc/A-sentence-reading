# 97 — Reader double-tap panel expand

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [63](63-mobile-reader.md) · [95](95-reader-swipe-nav.md)

## 무엇인가

문장 박스 **더블탭** → 문장만 전체 화면.  
그림 박스 **더블탭** → 그림만 전체 화면.  
꽉 찬 상태에서 다시 더블탭 → 분할 원복. (~280ms 애니메이션)

| 포함 | 미포함 |
|------|--------|
| `_ReaderLayoutMode` split/sentenceOnly/figureOnly | 웹 · 제스처 튜토리얼 |
| 더블탭 + AnimatedContainer 높이 | 핀치줌과 더블탭 줌 |
| pytest contract | Live Enable / IPS |

## Product (locked this chip)

1. Double-tap sentence → text-only; again → split.  
2. Double-tap figure → figure-only; again → split.  
3. Swipe / TTS / 연습 unchanged.

## Kill / rollback

- restore always-split Expanded flex layout

## Version

**0.3.11** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
