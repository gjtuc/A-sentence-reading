# 106 — Ingest quality hang: Gemini timeout + GCS progress

Modules: `debone.py` · `vision_ocr.py` · `ingest_jobs_gcs.py` · `app.py` (`ingest_job_status`)  
받침: [14](14-vision-ocr-router.md) · [105](105-upload-fail-notify.md) · [71](71-mobile-upload-resume.md)

## 무엇인가

「추출 품질 보는 중」(stage `quality`, ~12%)에서 **수십 분 멈춰** 보이는 문제를 줄인다.

| 포함 | 미포함 |
|------|--------|
| Gemini text/vision 호출 **하드 타임아웃** | 품질맵 모델·프롬프트 교체 |
| 품질맵 타임아웃 → 기존 `text_ok` 폴백 | OCR/비전 가속·Tesseract |
| GCS job push 임계 **+5% → +1%** (12→16 반영) | 클라이언트 APK 필수 변경 |
| 미완료 job 폴링 시 GCS **재조회** (타 인스턴스 고착) | Live Enable / IPS |

## Product (locked)

1. 품질맵 Gemini가 응답 없으면 **타임아웃 후 text_ok**로 진행 (ingest 전체 실패 금지)
2. Vision 페이지 호출도 동일하게 타임아웃 → 해당 페이지만 스킵(기존 실패 경로)
3. 진행률이 1%라도 오르면 GCS에 반영되어 다른 Cloud Run 인스턴스 폴링이 따라옴
4. 알림/로그에 API 키·이메일·토큰 금지

## Kill / rollback

- Revert PR · 타임아웃 상수만 키워 완화 가능

## Version

**0.3.20** · `app.version` + status (모바일 pubspec은 서버 전용 칩이라 필수는 아님)

## Device / pytest

- `_call_gemini` / `_call_gemini_vision` timeout → `TimeoutError`
- `gemini_quality_map` 타임아웃 → `quality_map_failed:…` + `text_ok`
- `should_push_job`: +1%면 push
- `ingest_job_status`: 미완료 로컬 캐시라도 GCS가 앞서면/종료면 갱신
- 실기: 신규 업로드가 품질 단계에서 무기한 12% 고착되지 않음 (타임아웃 후 진행 또는 폴백)

## Timeouts (locked)

| 호출 | 한도 |
|------|------|
| text (`_call_gemini`) | **90s** |
| vision (`_call_gemini_vision`) | **60s** / page |

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
