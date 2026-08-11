# 112 — Mid-stage ingest resume skip (use checkpoint payloads)

Modules: `ingest_jobs_gcs.py` · `api/app.py` · `vision_ocr.py`  
받침: [110](110-ingest-checkpoint-envelope.md) · [107](107-ingest-job-reclaim.md) · [71](71-mobile-upload-resume.md)

## 무엇인가

110 봉투를 **실제로 소비**한다. reclaim 시 유효한 checkpoint+payload가 있으면  
품질→비전→디본→번역에서 **이미 끝난 단계를 건너뛰고** 이어서 처리한다.  
실패·불일치·손상 시 봉투·payload를 버리고 **처음부터** (제품 잠금).

| 포함 | 미포함 |
|------|--------|
| `users/{uid}/ingest_payloads/{job_id}.json` 저장·로드·삭제 | 그림 PNG payload (재추출) |
| 완료 단계 skip + 비전 mid-page resume | 자체 APK 업데이트 · 드래그 UI |
| 진행률을 resume 지점 근처 %부터 | Live Enable / IPS |
| TTL 7일(체크포인트와 공유) · kill `ASR_INGEST_RESUME_SKIP=0` | |
| 소유자 경로만 · public poll에 본문 미노출 | |

## Product (locked)

1. 전 구간 skip 목표 (한 칩)  
2. resume 실패 → discard + full restart  
3. 중간 결과 ~7일  
4. UI: 이어받을 지점 message · %는 stage floor 근처  
5. 같은 PDF 자동 이어올리기(초안) 유지  
6. 본문/제목 전문을 poll·로그에 넣지 않음  

## Kill / rollback

- `ASR_INGEST_RESUME_SKIP=0` → payload 미사용 · 항상 전체 재시작 (envelope는 110)  
- Revert PR

## Version

**0.3.26** · status `ingest_resume_skip`

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / pytest

- unit: payload owner 격리 · invalid → full restart · vision resume start index  
- reclaim + fake GCS: skip prior stages (mock)  
- 실기: status flag + APK pin · 가능하면 소형 PDF 업로드 진행 확인  

## 후속 후보

- 보관함 드래그 하얗게 · 자체 APK 업데이트 · debone mid-chunk 정밀 resume

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
