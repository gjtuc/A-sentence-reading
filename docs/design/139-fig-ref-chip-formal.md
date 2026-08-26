# 139 — Fig. ref chip formalization (app + web)

Modules: `fig_refs` (py/js/dart) · web `app.js`/`styles.css` · mobile `reader_screen.dart` · `/api/status`  
받침: [28](28-fig-ref-jump.md) · [124](124-missing-figures.md)

## 무엇인가

본문 `Fig./Scheme/Table` → 그림 점프는 이미 있다.  
이번 칩은 **앱+웹**에서 **문장 아래 ghost 칩**으로 동작을 제품답게 맞추고, 서버 **킬스위치**를 웹도 따르게 한다.

| 포함 | 미포함 |
|------|--------|
| 앱: 문장 카드 **아래** 전용 칩 줄 (웹 `#figRefHints`와 같은 자리) | compound 1a/1b · DOCX |
| ghost/outline 칩 · 라벨 `Fig. N →` · 현재 칸 `is-current` | APK 자체 업데이트 |
| 매칭 실패 → 칩 없음 · 문장 인덱스 불변 | 인라인 본문 하이퍼링크 강제 |
| 킬 `ASR_FIG_REF_HINTS=0` → status false → 앱·웹 칩 숨김 | Live Enable / IPS |

## Product (locked)

1. **앱 + 웹** (B)  
2. **웹 패리티 칩 UI** (B): 문장 프레임/카드 **아래** 전용 줄 · ghost outline  
3. 클릭 → **figure_index만** 이동 (sentence 불변)  
4. 캡션 키 불일치 → **칩 없음** (가짜 점프 금지)  
5. 검증: **폰 + Live**  
6. DOCX 옆논문 · compound — **후보 삭제 · 이 칩에서도 안 함**

## Kill / rollback

- `ASR_FIG_REF_HINTS=0` → `fig_ref_hints=false` · 클라 칩 숨김  
- Revert PR · 이전 APK `0.3.56`

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.57** · pipeline 변경 없음 (`rich-v15`)

## Device / E2E pin

_(filled after phone + Live verification)_

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
