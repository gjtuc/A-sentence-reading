# 472 — 웹 한글 글꼴 · 애니메이션 꺼진 PC에서도 미끄러지기 · 웹 질문 칸은 얇게

## 바람

- 웹에서 가끔 한글 글자가 X 친 네모(⊠)로 깨진다. AI 질문을 치는 중에도 그렇다.
- 휠로 넘기기는 되는데 부드럽게 넘어가는 움직임(design/471)이 전혀 없다.
- 앱의 큰 질문 칸은 좋은데 웹은 3줄이 너무 넓다. 예전 높이나 두 줄이 좋다.

## 원인

- 웹 앱에는 한글 글꼴이 없다. Flutter 웹은 처음 보는 한글이 나올 때마다 Noto Sans KR 조각을
  Google에서 받아 온다. 받기 전까지 그 글자는 ⊠다. "AI로 묻기"의 "묻", "설명해줘"의 "줘"처럼
  아직 받지 않은 조각의 글자가 깨진다.
- 이 PC는 Windows "애니메이션 효과"가 꺼져 있다(`SPI_GETCLIENTAREAANIMATION` = False). 브라우저는
  이것을 `prefers-reduced-motion`으로 알리고, Flutter 웹은 `disableAnimations`로 받는다.
  `SentenceSlideSwitcher`가 그것을 따라 움직임을 껐다. 시험(휠·화살표 모두)에서는 움직임이 나왔다.

## 고침

- `assets/fonts/NotoSansKR-{Regular,Bold}.ttf`: Noto Sans KR(SIL OFL)을 KS X 1001 2,350자 +
  앱 코드에 쓰인 모든 한글 + 자모 + 한중일 문장 부호로 줄였다(각 0.76 MB, 압축 전송 약 0.35 MB).
  `scripts/make_web_hangul_font.py`로 다시 만든다.
- `app.dart`: 웹에서만 `fontFamilyFallback: ['NotoSansKR']`. 휴대폰은 시스템 한글 글꼴 그대로다.
  드문 글자(2,350자 밖)는 예전처럼 Google 조각으로 받는다.
- `SentenceSlideSwitcher`는 "움직임 줄이기"를 따르지 않는다. 앱의 다른 넘기기 움직임도 따르지 않는다.
- `AiAskQuestionField.compact`(웹 기본): 예전처럼 얇은 칸(`isDense`)이고 긴 질문은 두 줄까지 늘어난다.
  앱은 3~5줄 그대로다.

## 시험

- `tests/test_design_472_hangul_font.py` — 앱 코드의 한글이 모두 두 글꼴에 있다(없으면 스크립트를 다시 돌린다).
- `mobile/test/reader_wheel_471_test.dart` 끝의 design/472 시험 두 개.
