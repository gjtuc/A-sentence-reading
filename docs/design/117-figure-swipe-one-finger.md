# 117 — Figure swipe only on one-finger pan (not pinch)

Modules: `mobile/lib/screens/reader_screen.dart` · `mobile/lib/api/figure_swipe_gate.dart`  
받침: [116](116-figure-pinch-vs-swipe.md) · [95](95-reader-swipe-nav.md)

## 무엇인가

핀치로 확대한 뒤 **1×까지 다시 줄일 때**, 두 손가락이 아직 닿아 있어도  
가로 이동이 남아 있으면 116의 1× pan-end 스와이프가 **옆 그림으로 넘긴다**.

제품: **한 손가락** 스와이프만 이전/다음. **두 손가락** 제스처(핀치·1× 복귀 포함)는  
그림 번호 고정. 손가락을 모두 떼면 다음부터 다시 한 손가락 넘기기 가능.

| 포함 | 미포함 |
|------|--------|
| 제스처 중 max pointer ≥2 이면 스와이프 금지 | 핀치 민감도(별 칩) |
| 순수 게이트 함수 + 단위 테스트 | 웹 |

## Product (locked)

1. 넘기기 = **손가락 1개** 좌우 스와이프만  
2. 핀치(2+)로 1× 복귀 중/직후(손 떼기 전) → **넘기기 없음**  
3. 손 다 뗌 → 이후 한 손가락 스와이프 정상  

## Kill / rollback

- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.31**

## Device / pytest

- unit: `allowFigureSwipeAfterPan` 게이트  
- 실기: 1손가락 스와이프 넘김 · 핀치→1× 후(손 떼기 전) 그림 번호 유지
