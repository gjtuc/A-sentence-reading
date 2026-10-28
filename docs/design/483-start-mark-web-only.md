# 483 — 시작 표시는 웹에만, 밝아짐은 더 옅게

## 문제

사용자: 폰은 손으로 끌어야 문장이 넘어가니 불편하지 않다. 눈이 손을 따라가므로 새 문장의 시작을 찾을
일이 없다. 그리고 문장이 올 때 표시가 밝아지는 정도가 조금 세다.

## 방침

- 폰 읽기 화면은 `withStartMark(gutter: 0)` — 표시를 붙이지 않는다. 웹(휠·키로 넘김)은 그대로.
- `StartMark.peak` 0.55 → 0.3. 16% 에서 30% 로만 살짝 밝아진다. 3초에 걸쳐 사라지는 것(design/482)은
  그대로.
- 첫 줄 높이 고정(design/480)은 폰에서도 그대로 둔다. 보이는 것이 없고 넘길 때마다 읽기 시작 자리가
  같다.

## 확인

`reader_screen_widget_test.dart` "the phone shows no start mark", `sentence_anchor_480_test.dart`.
