# 116 — Figure pinch must win over swipe/double-tap (keep both)

Modules: `mobile/lib/screens/reader_screen.dart` (`_ZoomableFigureFrame`)  
받침: [94](94-figure-zoom-fill-frame.md) · [95](95-reader-swipe-nav.md) · [97](97-reader-panel-expand.md) · [115](115-reader-clip-without-decoration.md)

## 무엇인가

그림 **전체 화면**에서 핀치 줌이 안 되거나 끊기는 경우:  
부모 `GestureDetector`의 **좌우 드래그**가 `InteractiveViewer` 스케일과  
제스처 경쟁을 한다. 제품 선택: 넘기기·더블탭은 **화면 전체 유지**,  
충돌만 줄인다 (가장자리/버튼만으로 제한하지 않음).

| 포함 | 미포함 |
|------|--------|
| 1× 스와이프를 InteractiveViewer pan 종료로 감지 | 핀치 배율 가속(별 칩) |
| 부모에서 horizontal drag 제거 (tap/double-tap만) | 연습 HTTP 500 |
| 줌 중 setState 남발 축소 | 웹 줌 |

## Product (locked)

1. **1손가락** — 탭(chrome) · 더블탭(전체화면 토글) · 1×에서 좌우 넘기기  
2. **2손가락** — 핀치 줌 (분할·전체화면 동일)  
3. 줌 중(>1.02×)에는 넘기기 없음 · pan으로 이동  

## Kill / rollback

- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.30**

## Device / pytest

- flutter: 줌 프레임이 parent horizontal-drag 없음 · 계약 테스트  
- 실기: 그림 더블탭 전체화면 → 핀치로 확대 확인 · 1× 스와이프로 그림 변경
