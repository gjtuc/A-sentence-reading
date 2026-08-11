# 94 — Figure zoom fills frame

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [63](63-mobile-reader.md)

## 무엇인가

읽기 탭 그림 칸에서 확대 시 **이미지 원본 크기만** 커지고 프레임 안 검은 여백은 못 쓰는 구멍.  
`InteractiveViewer` 자식을 **프레임 전체 크기**로 두어 줌/팬이 칸을 쓰게 한다.

| 포함 | 미포함 |
|------|--------|
| `_ZoomableFigureFrame` (LayoutBuilder + full-size child) | 웹 캐러셀 줌 · crop UI |
| pytest contract | Live Enable / IPS |

## Product (locked this chip)

Zoom/pan must use the whole figure frame, not only the intrinsic image bounds.

## Kill / rollback

- restore bare `InteractiveViewer(child: Image…)`

## Version

**0.3.8** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
