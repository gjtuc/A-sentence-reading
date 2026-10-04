# design/390 — 다시 읽기의 정답은 단어 혼자 읽은 소리

## 문제

틀린 단어 다시 읽기는 단어 하나를 원어민 음성으로 새로 합성해 들려준다 (`synthesizeTts(text: word)`). 채점은 문장 안에서 그 단어가 났던 소리 (`item.phone`, `item.share`) 로 했다.

단어 혼자 읽으면 사전식 발음이 나오고, 문장 안에서는 앞뒤에 이어져 약해진다. 0.3.428 로그 (`onto`, 00:16–00:24):

- 문장 안 기준: `ʌ n d ə` (뒤에 CNT 가 붙어 약한 형태)
- 다시 읽기에서 들려준 소리: 단어 혼자, `ɑː n t uː` 계열
- 사용자가 낸 소리: 매번 `aː n t uː`
- 결과: ʌ · d · ə 가 계속 틀림, 단어·소리 연습 20번 넘게 불합격

채점 규칙(1단계·2단계, `twoGateWordScore` · `soundClears`)은 문장 연습과 같았다. 들려주는 것과 정답이 다른 발음이었다.

## 고친 것

- 문장 채점에서 틀린 단어가 정해지는 순간, 단어마다 `/api/tts/spoken` 을 단어 혼자로 물어 기준을 짓게 한다 (`wordOwnSpans`).
- 다시 읽기는 단어마다 시작할 때 그 기준을 받아 (`withOwnReference`) 그 단어의 발음기호·분포로 채점한다. 화면의 발음기호, 소리 사다리, 소리 연습도 같은 기준을 쓴다.
- 문장 채점 때의 소리별 점수는 다른 기호에 대한 점수이므로 버린다. 첫 다시 읽기의 점수부터 사다리가 쌓인다.
- 기준이 아직 없으면 1.5초마다 다시 묻고 최대 12초 기다린다. 그래도 없으면 예전처럼 문장 기준으로 채점하고 기록에 `review_ref=sentence` 를 남긴다.

기준 목소리는 문장과 같이 `reference_voice()` 다. 다시 읽기에서 들려주는 목소리는 무작위로 바뀌지만 문장 연습도 그렇다.

## 기록

- `practice_skill_review`: `review_ref` (`word` · `sentence`), `ref_phones`, `slot_each`, `slot_top`, `slot_said`, `score_pct`, `line_pct`, `bar_pct`
- 순환 단계 `review_word_ref`: `ref_code`, `ref_wait_ms`, 두 기준의 소리 수
- `slot_each` · `slot_top` 길이 제한 400자 → 2000자. 17단어 문장에서 끝 단어의 소리별 점수가 잘려 `onto` 를 기록에서 볼 수 없었다.

## 확인

- `mobile/test/miss_review_test.dart` design/390 네 개
- `tests/test_evidence_safe_details_cache_id.py` design/390
- 배포 뒤 다시 읽기 기록의 `review_ref` 가 `word`, `ref_wait_ms` 가 대부분 0 근처
