# 45 — Progressive 읽기 열기 (초벌→단계 갱신)

모듈: `models` · `llm/translate_section` · `api/app` ingest job · `static/app.js`  
받침: [40](40-ingest-section-translate.md) · [42](42-translate-ingest-only.md) · [43](43-translate-progress.md)

## 제품 결정 (합의)

| 항목 | 선택 |
|------|------|
| 언제 읽기 시작 | debone 후 **영어 먼저** 허용. 한글 없으면 「번역 진행 중」 |
| 단계 갱신 | draft→sense→polish→harmonize **단계마다** 저장. **보고 있는 문장 UI는 고정**, 다른 문장으로 이동 시 최신본 |
| 진행 표시 | 헤더/배지에 번역 진행 메시지 |
| 다시 열기 | 완료분은 **최종만**. 미완료는 이어서 |
| 탭 강제 종료 | 문장/캡션 `text_ko_stage` 로 어디까지 했는지 저장 후 재개 |
| 그림 자동 분리 | 끔 (44). 드래그 크롭만 |

## 이번 구현 (0.2.53 · 기초)

1. `Sentence.text_ko_stage` / `Figure.caption_ko_stage`  
   (`""` \| `draft` \| `sense` \| `polish` \| `harmonize`)
2. ingest: debone·문헌 추출 후 **partial 결과 공개** → UI가 세션 오픈  
3. 같은 job에서 번역 계속 · 단계마다 세션/캐시 갱신 · job `result` 갱신  
4. UI: partial 적용 · 현재 문장 KO 스냅샷 고정 · 빈 KO = 「번역 진행 중」  
5. 미완료 stage 있으면 백필/재개 (`needs_translate_backfill` 확장)

## 비목표 (이번)

- 번역 문장 **병렬** worker (후속)
- Live Enable / IPS — **Trading Gate 전용. ASR 밖** (구현·설계 변경 없음)
- Flutter
- compound 재활성

## 불변

- 읽기 인덱스 독립
- TTS = 영어
- 점수/채점 없음
- live `/api/translate` 읽기 폴백 없음 (42)

## 버전

0.2.53
