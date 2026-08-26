# 136 — Strip adjacent articles (keep first only)

Modules: `pdf/adjacent_articles.py` · ingest (`api/app.py`) · `llm/typography.py`  
받침: [02](02-pdf-extract.md) · [135](135-cover-as-figure.md) · fixture `testdata/adjacent_papers/`

## 무엇인가

한 PDF에 **논문이 여러 편** 붙어 있으면(호 통째·이어붙인 파일), 앞뒤 남의 논문 문장·그림이 섞인다.  
**첫 논문만** 남기고 뒤를 버린다. 경계를 못 정하면 **업로드 실패**(통째 처리 금지).

| 포함 | 미포함 |
|------|--------|
| 페이지 전면부 휴리스틱으로 논문 시작점 탐지 | 사용자가 구간을 고르는 UI |
| 시작점 ≥2 → 첫 구간만 남긴 PDF로 교체 후 ingest | 가장 긴 논문 선택 · 중간 논문만 추출 |
| 다중 신호인데 절단점 불명 → job 실패 | DOCX · 캡션 쪼개기 · 로컬 서버 흔적 제거 |
| 킬 `ASR_STRIP_ADJACENT=0` · pipeline `rich-v14` | Live Enable / IPS |

## Product (locked)

1. **첫 논문만** 유지, 이후 페이지 폐기  
2. 단일 논문(시작점 1개) → 자르지 않음  
3. 다중으로 보이는데 **경계를 못 찾으면 실패** (fail-closed · 통째 성공 금지)  
4. 참고문헌에 옆 논문 제목이 **인용**된 것은 새 시작으로 치지 않음  
5. 검증: **폰 + Live** (합성 fixture · 가능하면 OA merge)

## Kill / rollback

- `ASR_STRIP_ADJACENT=0` → status `strip_adjacent=false` · trim/fail 로직 끔(옛 통째 처리)
- Revert PR · `PIPELINE_VERSION` 되돌림

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.54** · pipeline **rich-v14**

## Security / multi-user

- Trim runs **inside the owner’s ingest job** on that upload’s temp PDF only — no `user_id` from client body.
- Fail-closed refuses ambiguous multi-paper PDFs (no silent whole-file success).
- Kill: `ASR_STRIP_ADJACENT=0` (Cloud Run env) restores prior whole-PDF ingest.

## Device / E2E pin

_(filled after phone + Live verification)_

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
