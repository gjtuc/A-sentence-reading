# 475 — 말로 AI에게 묻기, 테마 하나로, 미끄러짐이 끝까지 보이게

## 1. 휠로 넘길 때 미끄러짐 (0.3.488 뒤에도 안 보임)

### 원인

이 PC는 Windows "애니메이션 효과"가 꺼져 있다. 브라우저는 이것을 "움직임 줄이기"로 알리고, Flutter는
`SemanticsBinding.disableAnimations` 가 켜지면 모든 `AnimationController` 를 원래 길이의 5%로 돌린다
(`animation_controller.dart`: `animationBehavior._enableAnimations ? 1.0 : 0.05`). 0.28초가 0.014초가
되어 한 장면 안에 끝났다. design/472가 `MediaQuery` 의 값만 무시했고, 컨트롤러 쪽은 그대로였다.

### 고침

`SentenceSlideSwitcher` 의 컨트롤러에 `animationBehavior: AnimationBehavior.preserve`.

시험은 `tester.platformDispatcher.accessibilityFeaturesTestValue` 로 이 설정을 켠다. 고치기 전 코드에서는
움직임이 0이라 실패하고, 고친 뒤에는 통과한다.

## 2. 테마 하나로

### 바람

설정에 "테마"(시스템/밝음/어둠)와 "화면 색"(앱 테마/어두운 회색/종이색/흰색)이 같이 있고, 어두운 회색과 어둠이
사실상 같다.

### 고침

- 웹과 폰 모두 설정 위쪽의 **테마** 하나: 시스템 / 밝음 / 어두움 / 종이.
- 밝음 = 예전 흰색, 어두움 = 예전 어두운 회색, 종이 = 예전 종이색. 시스템은 기기 설정에 따라 밝음과 어두움.
- 값은 예전 "화면 색" 자리(`WebPage`)에 그대로 저장한다. 웹은 `web_reading_page_v1`, 폰은 `reader_page_v1`.
- 폰에서 지금까지 쓰던 것은 그대로 보인다(`phoneThemeChoice`): 화면 색을 골라 뒀으면 그 색, "앱 테마"였으면
  옛 테마(밝음 → 밝음, 어둠 → 어두움, 시스템 → 시스템). 폰에서 테마를 한 번 고르면 옛 테마는 시스템으로 돌려서
  더 이상 끼어들지 않는다.
- 폰 읽기 설정과 웹 읽기 화면 설정에 있던 "화면 색"은 지웠다.

## 3. 말로 AI에게 묻기

### 바람

- 다른 AI처럼 잠깐 쉬면 질문이 끊기는 방식은 싫다. 충분히 말한 다음 한 번에 글자로 바꾼다.
- 말하는 동안 화면 전체가 목소리에 맞춰 차분하게 일렁이고, 아무 곳이나 누르면 질문이 끝난다.
- 한국어와 영어를 섞어 말한다.
- 보내는 질문은 영어 문장 + "음성으로 받아 적었으니 감안해 달라"는 한 줄 + 질문.

### 흐름

1. 질문 칸 오른쪽의 마이크(`ai_ask_mic`)를 누른다. 꾹 눌러 여는 아래 시트와 웹에서 글쇠로 여는 질문 창 모두.
2. 전체 화면이 열린다. 가장자리에 여러 색의 부드러운 띠가 천천히 돌고, 목소리가 크면 넓고 밝아진다.
   가운데 "음성으로 질문하는 중이에요. / 아무 곳이나 누르면 질문이 끝나요.", 시간, "한국어와 영어를 섞어
   말해도 돼요." 아래에 작은 "취소".
3. 조용해도 끊지 않는다. 끝나는 것은 화면 누르기(PC는 Enter/Space도), 3분이 지났을 때뿐이다.
   취소는 "취소", 폰 뒤로 가기, PC Esc.
4. 누르면 녹음을 서버로 보내고 "글자로 바꾸는 중이에요…". 받아 적은 글은 **질문 칸에 들어가고**, 확인하거나
   고친 뒤 보낸다.
5. 보낼 때 질문 앞에 한 줄을 붙인다:
   `이 질문은 음성 인식으로 받아 적어서 틀린 글자가 있을 수 있어요. 소리가 비슷한 말로 이해해 주세요.`
   받아 적은 글을 고쳐도 붙는다. 칸을 다 지우고 새로 쓰면 붙지 않는다.
6. 실패하면 그 화면에 이유와 "다시 말하기". 마이크 거부, 빈 녹음, 알아들은 말 없음, 로그인 필요, 연결 끊김.

일렁임은 `AnimationController` 가 아니라 `Ticker` 로 그린다. 1번과 같은 PC에서도 움직이게.

### 소리 크기

- 웹: 열려 있는 마이크 스트림에 `AnalyserNode` 를 붙여 한 장면의 RMS. 연습 화면은 이것을 묻지 않으므로
  만들어지지 않는다.
- 폰: `asr/shadowing_mic` 에 `level` 호출 → `MediaRecorder.getMaxAmplitude()` (지난 호출 뒤의 최고값).
  이 호출이 없는 옛 앱은 0(조용함)으로 읽는다.
- 둘 다 -50 dB를 0, 최대를 1로 (`micLevelFromRms`, `micLevelFromAmplitude`). 빨리 올라가고 천천히 내려온다.

### 서버

`POST /api/ask/voice` (파일 + `sentence`) → `{ok, text, ms}`. 유료 기능 문(`paid_access_denied`)을 지난다.
`voice_question.transcribe_question` 이 Gemini(`gemini_model()`)에 녹음과 화면의 영어 문장을 함께 준다.

- 한국어는 한글, 영어는 영어로. 문장에 있는 낱말은 문장의 철자대로.
- 음, 어, 그, uh, um 과 말 더듬기는 빼고, 나머지 말과 순서는 그대로. 답하거나 덧붙이지 않는다.
- 생각 토큰 0, 온도 0, 60초 제한, 녹음 12 MB 까지.

PC 음성(Heami)으로 "음... 이 문장에서 catalyst가 정확히 무슨 역할을 하는 거야? 어, 그러니까 반응 속도를
높인다는 거야?"를 만들어 보냈더니 "이 문장에서 catalyst가 정확히 무슨 역할을 하는 거야? 그러니까 반응 속도를
높인다는 거야?"가 돌아왔다. 첫 호출 14초(준비), 다음 4초.

### 증거

- 서버 `voice_ask_transcribe`: ok, code, 녹음 바이트, mime, 문장 글자 수, 받아 적은 글자 수, ms.
- 앱 `voice_ask_client`: `heard`, `cancel`(phase, via), `mic_denied`, `mic_failed`, `empty_take`,
  `nothing_heard`, `transcribe_failed`(error), 녹음 초.

## 시험

- `mobile/test/reader_wheel_471_test.dart` — design/475 애니메이션 꺼짐에서도 미끄러짐
- `mobile/test/web_reading_prefs_test.dart` — 테마 네 가지, 시스템의 밝음/어두움, 폰 옛 설정 옮기기
- `mobile/test/voice_ask_475_test.dart` — 마이크 없음/있음, 말하기→누르기→칸에 들어감→한 줄 붙음, 지우면 빠짐,
  취소와 Esc, 마이크 거부, 받아쓰기 실패와 다시, 빈 녹음
- `mobile/test/shadow_mic_test.dart` — 폰 `level`
- `tests/test_design_475_voice_question.py` — 증거 종류, mime, 정리, 빈/큰 녹음, 문장 전달, 라우트
