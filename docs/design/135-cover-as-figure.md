# 135 — Title-page cover as figure 1

Modules: `pdf/extract.py` · `llm/typography.py` (`PIPELINE_VERSION`) · status flags  
받침: [02](02-pdf-extract.md) · [92](92-figure-caption-order.md) · [125](125-caption-anchored-figures.md)

## 무엇인가

일부 논문은 **표지(제목·저자 페이지)** 가 그림 캐러셀에 안 들어가거나 뒤로 밀린다.  
제목·저자처럼 보이는 첫 페이지만 **그림 슬롯 1번(index 0)** 으로 앞에 둔다.

| 포함 | 미포함 |
|------|--------|
| 페이지 0 휴리스틱(제목·저자 신호) → 전면 클립 | 무조건 첫 페이지 삽입 |
| 캡션 `Title page (p.1)` · 정렬 키 Fig/GA보다 앞 | 옆 논문 페이지 제거 |
| pipeline `rich-v13` · 재분석으로 옛 보관본 갱신 | 캡션 덩어리 쪼개기 · APK 자체 업데이트 |
| 킬 `ASR_COVER_AS_FIGURE=0` | Live Enable / IPS |

## Product (locked)

1. **휴리스틱 (B)**: 제목·저자·소속·DOI 등 표지 신호가 있으면 넣고, 본문/서론만 보이면 **안 넣음**
2. 넣으면 캐러셀 **맨 앞** (index 0); Fig. 1 번호는 캡션 그대로(슬롯 위치만 앞)
3. 검증: **폰 + Live** (재분석 또는 새 업로드 후 그림 1번이 표지)
4. 실패·애매하면 fail-closed: **커버 슬롯 없음** (가짜 표지 금지)

## Kill / rollback

- `ASR_COVER_AS_FIGURE=0` → status `cover_as_figure=false` · extract skip
- Revert PR · `PIPELINE_VERSION` 되돌리면 옛 추출 (재분석 전 캐시는 구버전)

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.53** · pipeline **rich-v13**

## Device / E2E pin

- Live `/api/status`: `version=0.3.53` · `pipeline_version=rich-v13` · `cover_as_figure=true`
- pytest `tests/test_cover_as_figure.py`: heuristic accept/reject · prepend · kill `ASR_COVER_AS_FIGURE=0`
- Local extract: journal DRM PDF + synthetic title PDF → first caption `Title page (p.1)`
- APK SM-G986N → Live: upload `zzz_asr_cover135.pdf` → library **5→6** · open reader → **figure 1 / 2** · caption **`Title page (p.1)`**
- Kill: `ASR_COVER_AS_FIGURE=0` · revert PR · prior pipeline

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
