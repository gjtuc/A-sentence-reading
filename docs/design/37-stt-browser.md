# 37 — 브라우저 STT 발음 연습 (점수 없음)

모듈: `stt/compare.py` · `POST /api/stt/compare` · `stt_practice.js` · 헤더 「말하기」  
후속: 서버 STT (브라우저 검증 뒤)

## 무엇을

현재 영어 문장을 **소리 내어 읽으면**, 브라우저 Web Speech API가 글자로 받아 적고,  
원문과 **단어 단위 차이(diff)** 만 보여 준다.

- **점수·등급·AI 채점 없음** (표시 금지)
- 기대 문장 / 인식 문장 / 맞음·빠짐·추가 하이라이트

## 비목표 (이번)

- 서버 STT · 오디오 업로드 인식
- 발음 점수·유창성 AI
- Live Enable / IPS (Trading Gate — ASR 밖)
- Flutter
- 번역·TTS 동작 변경

## API

`POST /api/stt/compare`  
Body: `{ "expected": "<en>", "heard": "<en>" }`  

성공:

```json
{
  "ok": true,
  "expected_tokens": ["..."],
  "heard_tokens": ["..."],
  "diff": [
    { "op": "equal", "expected": "the", "heard": "the" },
    { "op": "replace", "expected": "catalyst", "heard": "catalysis" },
    { "op": "delete", "expected": "was", "heard": null },
    { "op": "insert", "expected": null, "heard": "uh" }
  ]
}
```

실패: `invalid_expected` · `invalid_heard` · (둘 다 비어 있으면) `empty`

정규화: 소문자 · HTML 제거 · 문장부호를 공백으로 · 연속 공백 축소.  
**INVARIANT:** 응답에 `score` / `grade` / `accuracy` 필드를 **넣지 않는다**.

## UI

- 헤더 **말하기** 토글 (녹음/인식 중 `aria-pressed`)
- Chrome 등 `SpeechRecognition` / `webkitSpeechRecognition` (`lang=en-US`, interim 결과 표시)
- 미지원 브라우저: 짧은 안내 (기능 크래시 없이)
- 인식 종료·중지 시 `/api/stt/compare` 호출 → `#sttDiff` 렌더
- 문장 인덱스가 바뀌면 패널 초기 (읽기 루프 방해 최소화)

## Prefs

없음 (이번). 켜짐 상태는 세션 내 UI만.

## 불변

- INVARIANT: 채점 숫자/등급를 UI·API에 노출하지 않음
- INVARIANT: STT는 문장/그림 인덱스를 바꾸지 않음
- INVARIANT: 노트 MediaRecorder 보이스와 **별개** (연습용 인식만)

## 버전

0.2.45
