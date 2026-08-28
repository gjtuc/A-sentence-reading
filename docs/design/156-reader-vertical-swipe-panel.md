# 156 — Reader vertical swipe between full-screen panels

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [97](97-reader-panel-expand.md) · [118](118-figure-pinch-sensitivity.md)

## 무엇인가

| 상태 | 제스처 | 결과 |
|------|--------|------|
| figure full (`figureOnly`) | 아래로 스와이프 @ 1× | sentence full (`sentenceOnly`) |
| sentence full (`sentenceOnly`) | 위로 스와이프 | figure full (`figureOnly`) |
| split | (무시) | 스플릿 바·더블탭이 담당 |

split 복귀는 **더블탭만** (design/97 유지).

## 구현

- `_swipeToSentenceFromFigure` / `_swipeToFigureFromSentence`
- Figure: `_ZoomableFigureFrame` pan-end, `dy > dx`, `dy > 88px` or velocity
- Sentence: `_SwipePager.onSwipeUp` when `onSwipeToFigure` set
- Zoomed figure pan: `amplifyFigurePanExtraDelta` (design/118, `kFigurePanSensitivity = 1.85`)

## Version

**0.3.83**
