# 118 — Figure pinch sensitivity (clearly noticeable)

Modules: `mobile/lib/api/figure_pinch_sensitivity.dart` · `mobile/lib/screens/reader_screen.dart`  
받침: [94](94-figure-zoom-fill-frame.md) · [116](116-figure-pinch-vs-swipe.md) · [117](117-figure-swipe-one-finger.md)

## 무엇인가

핀치로 그림을 확대/축소할 때 **손가락 이동량 대비 배율 변화**가 약해 보인다는 피드백.  
제품 잠금: **확실히 체감** (살짝이 아님). 제스처 계약(117 한 손가락 넘기기)은 유지.

| 포함 | 미포함 |
|------|--------|
| 순수 `amplifyFigurePinchScale` + InteractiveViewer 후보정 | 쉐도잉 500 · 설정 카피 |
| sensitivity 상수(문서화) | 웹 줌 |
| min/max clamp 유지 (1× … 8×) | maxScale 상한 변경을 “민감도”로 위장 |

## Product (locked)

1. 같은 손가락 벌림 → **이전보다 분명히** 더 확대/축소  
2. 1×·한 손가락 스와이프·2손가락 넘기기 금지(117) 유지  
3. 과확대 상한 **8×** 유지 (민감도와 별개)

## Kill / rollback

- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.32**

## Device / pytest

- unit: `rawScale` → amplified (`pow`, sensitivity **1.85**) · 비정상 입력 fail-safe  
- 실기: 동일 소폭 핀치로 확대가 눈에 띄게 · 그림 번호 불변 · 손 뗀 뒤 한 손가락 넘기기 가능
