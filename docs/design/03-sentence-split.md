# 03 — Sentence split

모듈: `pdf/sentences.py`

## 목표

`raw_text` → `list[Sentence]`  
UI에 **한 번에 하나** 올릴 단위.

## 1차 알고리즘

1. 입력이 비면 `[]`
2. `pysbd.Segmenter(language="en", clean=False)` 사용 (논문 영어 가정)
3. 각 segment `strip()`; 빈 문자열 drop
4. 길이 > 800자인 segment는 **그대로 한 문장으로 둠** (임의 절단 금지 — 사용자가 한눈에 못 보면 그건 UX 문제이지 잘라서 해결하지 않음)
5. `id = sent_{i:06d}`, `start_char`/`end_char`는 raw에서 `str.find` 순차 검색 (실패 시 null)

한국어 논문: 1차 비목표. 나중에 `language` 세션 필드로.

## 약어·함정 (반드시 픽스처)

아래가 **한 문장 안에서 끊기면 회귀 실패**:

| 입력 조각 | 기대 |
|-----------|------|
| `see Fig. 1 for details.` | 문장 1개 |
| `Smith et al. reported` | 문장 경계 아님 |
| `i.e. the rate` / `e.g. Ni` | 경계 아님 |
| `vs. bulk` / `cf. Ref.` | 경계 아님 |
| `No. 3 sample` | 경계 아님 |
| `The end. Next claim starts.` | 문장 2개 |

`pysbd`가 이미 처리하면 그대로 신뢰. 깨지면:

- `# NEXT:` 전처리로 약어를 플레이스홀더로 치환 → 분할 → 복원  
- 또는 후처리로 `^[A-Z]`가 아닌 조각 merge

## 본문이 아닌 것

추출 단계에서 못 걸러낸 잡음:

| 패턴 | 처리 |
|------|------|
| 단독 페이지 숫자 `^\d+$` | drop |
| `References` / `REFERENCES`만 있는 줄 | drop |
| `http://`만 있는 줄 | drop |
| 길이 < 3 | drop |

캡션 전체가 본문에 중복 삽입되는 문제는 1차 허용 + warning `possible_caption_dup`.

## 출력 한도

- 문장 0개 → 세션은 만들어지되 UI empty ([06](06-ui-states.md)), warning `no_sentences`
- 문장 > 5000 → ingest 실패 `payload_too_large`

## 단위 테스트 파일

`tests/test_sentences.py` + `tests/fixtures/text/abbrev_cases.jsonl`  
각 줄: `{"text": "...", "count": N}`
