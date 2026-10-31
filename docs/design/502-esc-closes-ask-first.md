# design/502 — 전체 화면에서 Esc 는 위에 뜬 창부터, 문장 시작 표시 절반 밝기 (0.3.514)

## 왜

- 웹 전체 화면에서 AI에게 묻기 창을 Esc 로 닫으려 하면 창은 그대로이고 전체 화면만 풀렸다. 브라우저가 짧은 Esc 를
  전체 화면 끝내기에 먼저 써서 앱이 그 키를 받지 못했다.
- 문장이 넘어갈 때 첫 줄 왼쪽에 잠깐 밝아지는 막대(design/482)가 아직 너무 밝았다.

## 결정

- 전체 화면이 되면 `navigator.keyboard.lock(['Escape'])` (크롬·엣지). 짧은 Esc 는 앱이 받고, Esc 를 길게 누르면
  브라우저가 전체 화면을 끝낸다. 풀리면 `unlock`.
- 짧은 Esc 는 위에 뜬 창(대화 상자)이 먼저 쓴다. 아무 창도 쓰지 않은 Esc 는 `fullScreenTakesEscape` 가 전체 화면을
  끝낸다. 읽기 화면은 직접, 다른 화면은 window 의 bubble `keydown` (앱이 쓴 키는 `defaultPrevented`) 으로.
- 읽기 화면 Esc 는 눌러 둔 반복을 받지 않는다. 길게 누를 때 창 닫기 → 전체 화면 끝 → 뒤로 까지 번지지 않게.
- `StartMark.rest` 0.16 → 0.08, `peak` 0.3 → 0.15.

## 시험

- `mobile/test/full_screen_test.dart` — 쓰이지 않은 Esc 는 전체 화면을 끝내고 뒤로 가지 않음.
- `mobile/test/sentence_anchor_480_test.dart` — 밝기 절반.
