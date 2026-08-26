# 143 — Flip reader swipe direction (gallery convention)

Modules: `mobile/lib/screens/reader_screen.dart` · docs `95`  
받침: [95](95-reader-swipe-nav.md) · [117](117-figure-swipe-one-finger.md)

## 무엇인가

문장·그림 가로 스와이프 방향을 **일반 갤러리/페이지 관례**로 맞춘다.

| 포함 | 미포함 |
|------|--------|
| 손가락 **왼쪽** → **다음** · **오른쪽** → **이전** (문장 `_SwipePager` + 그림 1×) | 웹 스와이프 · 애니메이션 |
| design/95 제품 문장 정정 | 핀치/한손가락 게이트(117) 변경 |
| APK 버전 핀 | Live Enable / IPS · 보관 재분석 |

## Product (locked)

1. Swipe **left** (finger moves left / `dx < 0`) = **next** sentence or figure.  
2. Swipe **right** (`dx > 0`) = **previous**.  
3. Figure still only at 1× · one-finger (95/117 unchanged).  
4. ←/→ 버튼 의미는 그대로 (왼쪽 버튼=이전 · 오른쪽=다음).

## Kill / rollback

- Revert PR · restore left→prev / right→next mapping in `_SwipePager` + figure pan-end.

## Version

**0.3.59**

## Device / E2E pin

- Live `/api/status`: `version=0.3.59` (post-CD)
- Code: sentence `_SwipePager` + figure pan-end — `dx < 0` → next · `dx > 0` → prev
- pytest `tests/test_swipe_direction_flip.py`
- Phone: rebuild/sideload APK `0.3.59` then confirm left swipe advances sentence/figure
- Kill: revert PR

Do not paste emails, cookies, tokens, or secrets into chat/PR.
