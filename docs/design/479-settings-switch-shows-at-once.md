# 479 — 설정의 끊어 보기 스위치가 바로 바뀌어 보이게

## 증상

설정에서 "긴 문장 끊어 보기 (시험)"를 누르면 값은 저장되는데 스위치 모양은 그대로다. 설정을 나갔다가 다시 들어와야
바뀌어 보인다. 그래서 웹에서 끊어 보기가 안 되는 것처럼 보였다. 웹과 폰 모두 같다.

## 원인

`_ClauseBreakSwitch` 와 `_ReadingFontChoice` 는 스스로 듣지 않고 "듣는 쪽 안에 두라"고 되어 있었다. 실제로 읽기
화면 설정의 `ListenableBuilder` 안에 있었지만 `const` 로 놓여 있었다. Flutter는 다시 그릴 때 위젯이 같은 const
인스턴스이면 그 아래를 다시 만들지 않는다. 그래서 바깥은 다시 그려져도 스위치와 글꼴 칩은 옛 값을 계속 보였다.

## 고침

두 위젯이 `WebReadingPrefs` 를 스스로 듣는다(`ListenableBuilder`). 시험에서 쓰려고 `ClauseBreakSwitch`,
`ReadingFontChoice` 로 이름을 공개했다.

## 시험

- `mobile/test/settings_switch_479_test.dart` — 누르자마자 스위치가 켜지고 꺼짐, 글꼴 칩이 바로 골라짐
