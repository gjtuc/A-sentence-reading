# design/503 — 문장 넘기면 자동으로 읽기, 설정 정리 (0.3.515)

## 왜

- 문장을 들을 사람은 매번 스피커 버튼을 누르지 않고 넘길 때마다 듣고 싶다. 문장 창의 play TTS 버튼은 그래서 없앤다.
- 휘리릭 넘길 때마다 TTS 를 부르면 비용이 샌다.
- "마우스가 멈추면 버튼 숨기기"(design/414)는 끌 이유가 없었다.
- 설정 화면에 제목 없이 섞인 스위치가 있었고, 웹 읽기 칸에 모양과 동작이 몰려 있었다.

## 결정

- TTS 설정에 "문장 넘기면 자동으로 읽기" (`asr_tts_auto_read_v1`, 기본 꺼짐). 이 창에서 옮긴 문장
  (`LibraryController.onOwnSentenceMove`: `advanceSentence`·`goToSentenceIndex`)에 `kTtsAutoReadDelay` 0.7초 머물면
  `playCurrentSentence`. 다른 기기·그림 창에서 따라온 이동, 그림만 보이는 창, 연습 화면 아래(`TickerMode` 꺼짐)에서는
  읽지 않는다.
- `TtsController._playGen`: 받는 중에 문장을 옮기면 늦게 온 소리는 버린다.
- 문장 창의 play/stop TTS 버튼 삭제 (웹·휴대폰). 받는 중 표시와 TTS 오류 글은 남긴다. 다시 듣기는 앞뒤로 옮겼다 오면 된다.
- 버튼 숨기기는 항상 켜짐. `WebReadingPrefs.autoHide` 와 스위치 삭제.
- 설정 순서: 계정 · 테마 · 읽기 화면 (웹은 + 읽기 동작) · TTS · 기능(번역·참고문헌·따라 말하기) · 앱을 열면 · 앱 정보 ·
  초대 코드 · 관리자.

## 시험

- `mobile/test/reader_screen_widget_test.dart` — 빠르게 두 번 넘기면 0번, 머물면 1번, 끄면 0번. TTS 버튼 없음.
- `mobile/test/web_reading_prefs_test.dart` — autoHide 빠짐.
