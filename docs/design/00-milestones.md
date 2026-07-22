# 00 — Milestones

구현을 **한 번에 다 하지 않는다.** 각 단계가 끝나면 수동/자동으로 검증 가능하게.

## M0 — Skeleton (현재, 완료)

- mock UI, 독립 네비, Immersive식 CSS, PDF stub
- 합격: `/api/status` · `/api/session/mock` · 화살표 동작

## M1 — Data + API 계약 (코드 최소)

**목표:** 실 PDF 없이 계약만 고정.

- `models` 필드를 [01-data-model.md](01-data-model.md)에 맞게 확장 (필요 시)
- `POST /api/ingest` 가 **가짜 성공 경로**를 갖되, 실제 extract 호출 전 스키마만 맞춤  
  (또는 OpenAPI 예제 + Pydantic 모델만 추가)
- `GET /api/session/{session_id}` 추가 (메모리 1개 세션도 가능)
- 합격: 클라이언트와 서버가 같은 JSON 키를 씀 ([04-api-contract.md](04-api-contract.md))

## M2 — PDF 텍스트만

**목표:** 문장 패널에 **진짜 논문 문장**이 보이게.

- `extract_text` 실구현 ([02-pdf-extract.md](02-pdf-extract.md) §텍스트)
- `split_into_sentences` 실구현 ([03-sentence-split.md](03-sentence-split.md))
- ingest → figures는 비어 있어도 됨 / 문장만 채워도 OK
- 합격: 샘플 PDF 1개로 Sent N/M 이 0이 아니고, `Fig.` 가 문장 중간에서 안 끊김 (픽스처)

## M3 — PDF 그림

**목표:** 하단 캐러셀에 추출 그림.

- `extract_figures` ([02](02-pdf-extract.md) §그림)
- 이미지를 `data/extracted/{session_id}/` 에 저장 후 URL로 서빙
- 합격: 샘플 PDF에서 그림 ≥1, 넘기기 가능. 로고/아이콘 대량 혼입은 허용하되 필터 규칙 문서와 일치

## M4 — UI 연결 + 상태

- 파일 선택 → ingest → 세션 로드
- [06-ui-states.md](06-ui-states.md) loading/error/empty
- 합격: mock 없이도 로컬 PDF로 전체 루프

## M5 — 진행 저장 (선택)

- `localStorage` 또는 서버 사이드 `progress.json` ([05](05-session-store.md))
- 합격: 새로고침 후에도 같은 PDF면 문장/그림 인덱스 복원

## 명시적 연기 (M5 이후)

- compound figure (1a/1b) 분해
- Fig. N → 그림 자동 점프 힌트
- TTS / 음절 / 품사 색
- 다단 reading-order ML (전면; 의심 페이지 vision 우회는 [14](14-vision-ocr-router.md)로 일부 커버)

### 구현됨 (참고)

- OCR 스캔본 → **적응형 Gemini vision** ([14-vision-ocr-router.md](14-vision-ocr-router.md), `rich-v3`)

## 한 줄 규칙

새 기능을 넣을 때 **어느 M에 속하는지** PR/커밋 메시지에 적는다. M 밖이면 설계 문서부터 수정.
