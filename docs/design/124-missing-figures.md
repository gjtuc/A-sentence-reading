# 124 — Missing figures: honest empty slots + mobile Fig.N jump

Modules: `paper_cache.py` · `fig_refs` (py/js/dart) · `reader_screen.dart` · `app.js`  
받침: [02](02-pdf-extract.md) · [28](28-fig-ref-jump.md) · [06](06-ui-states.md)

## 무엇인가

읽기에서 그림이 **있는 척** 사라지거나, 본문 `Fig. N`으로 **점프할 수 없는** 구멍을 막는다.

| 포함 | 미포함 |
|------|--------|
| 캐시 PNG 유실 시 캡션 슬롯 유지 + 빈 이미지 안내 | PDF 신규 추출 휴리스틱(캡션 위/벡터) |
| 앱 문장 패널 Fig./Scheme/Table 칩 → 그림만 이동 | compound 1a/1b 분해 (design/28 밖) |
| 웹 broken `image_src` onerror 솔직 안내 | 캡션 말줄임 개선 (다음 칩) |
| 앱+웹 | APK 자체 업데이트 |

## Product (locked)

1. **B** — 앱 + 웹  
2. **C** — 목록 + 실제 이미지(또는 정직한 빈 칸) + Fig. N 점프  
3. **A** — 진짜 없으면 빈 칸/안내 (성공 위장 금지)  
4. 「Effect of metal…」로 재현·검증  
5. APK 업데이트 계속 뒤로  
6. 백로그 순서 유지  

## 재현 메모 (실기)

- Effect of metal: carousel `figure N / 3`, 캡션·이미지 표시됨  
- 앱 Fig. 칩: design/124에서 배선 · **UI 정식화는 design/139** (문장 카드 아래 outline)  
- 캐시 load가 PNG 없으면 figure **행 자체 삭제** → 목록에서 “실종” (정직하지 않음) — 124에서 유지 슬롯으로 고침

## Kill / rollback

- Revert PR / 이전 APK  
- 칩 UI: status `fig_ref_hints` false면 앱도 칩 숨김 (서버 기존 플래그 · design/139 `ASR_FIG_REF_HINTS=0`)

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.38**

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
