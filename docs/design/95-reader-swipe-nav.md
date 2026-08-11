# 95 — Reader swipe prev/next

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [63](63-mobile-reader.md) · [94](94-figure-zoom-fill-frame.md)

## 무엇인가

문장·그림 박스에서 **가로 스와이프**로 이전/다음.  
그림은 **확대되지 않은 상태(1×)** 에서만 스와이프 (줌 팬과 충돌 방지).

| 포함 | 미포함 |
|------|--------|
| 왼쪽→이전 · 오른쪽→다음 (문장·그림) | 웹 스와이프 · 애니메이션 페이지 전환 |
| 그림: scale≈1 일 때만 · `panEnabled` when zoomed | 세로 스크롤 대체 |
| pytest contract | Live Enable / IPS |

## Product (locked this chip)

1. Sentence card: swipe left = previous, swipe right = next (stops TTS).  
2. Figure frame: same, **only when not zoomed**.

## Kill / rollback

- remove `_SwipePager` / figure swipe hooks

## Version

**0.3.9** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
