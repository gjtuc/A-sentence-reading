# design/499 — 웹: 스페이스 바로 바로 말로 묻기 (0.3.512)

## 왜

- 웹 리더에서 글자를 치면 곧바로 글로 묻는 창이 열린다 (design/419). 말로 묻기는 마우스로 문장 카드를 길게 누르고
  마이크를 또 눌러야 했다. 사용자는 키보드만으로 말로 묻고 싶어 했다.

## 무엇

- `aiAskSpeaksOnKey`: Ctrl·Alt·Cmd 없이 누른 스페이스 바 (KeyDown 만). 글자 키 판정 `aiAskOpensOnKey` 는 그대로 스페이스를 거른다.
- `_onReaderKey` 는 스페이스면 `showAiAskTypeDialog(listenFirst: true)` 를 연다. 묻기 칸 `AiAskQuestionField` 가 첫 화면 뒤에
  곧바로 듣기 화면(design/475)을 띄운다. 듣기 화면은 원래 스페이스·Enter 로 질문을 끝낸다.
  그래서 스페이스 → 말하기 → 스페이스 → (글자 확인) → Enter 로 보낸다.
- 그림만 보이는 창에서는 스페이스를 쓰지 않는다 (그림 묻기에는 마이크가 없다).
- 설정의 넓은 화면 안내에 "글자를 치면 글로, 스페이스 바를 누르면 말로 AI에게 묻습니다." 를 붙였다.

## 시험

- `mobile/test/voice_ask_475_test.dart` — 스페이스만 말하기, 듣기 화면으로 열리고 스페이스로 끝나 글자가 칸에 들어감.
