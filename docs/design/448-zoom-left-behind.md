# 448 — 확대한 채 전체 화면을 풀면 그림이 사라지던 것 (0.3.472)

## 문제

그림을 두 번 눌러 전체 화면으로 하고 확대한 뒤 다시 두 번 눌러 풀면 아래 칸이 비었다. 폰과 웹 모두.
확대 상태(`TransformationController`)는 전체 화면 크기에서 잰 배율과 이동인데, 작은 칸에서도 그대로 쓰여
그림이 칸 밖으로 밀려나 있었다.

## 바꾼 것 (`_ZoomableFigureFrameState`, `reader_screen.dart`)

- 전체 화면을 켜고 끄는 두 번 누르기는 확대를 먼저 푼다 (`_onDoubleTap` → `_resetZoom`).
- 다른 길(밀어서 전환 등)로 칸 크기가 바뀌어도, 확대를 시작할 때의 칸 크기(`_zoomFrameSize`)에서
  가로나 세로가 1/3 넘게 달라지면 다음 프레임에 확대를 푼다.
  웹에서 마우스가 멈춰 버튼 줄이 접히는 정도는 이보다 작아서 확대가 남는다.
- 1배로 돌아온 제스처는 `_zoomFrameSize` 를 비운다.

## 시험

`mobile/test/reader_screen_widget_test.dart` — "the double tap that leaves full screen drops the zoom"
