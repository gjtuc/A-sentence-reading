# 142 — Remove keyboard sentence notes (keep recording practice)

Modules: web `app.js` · `index.html` · `/api/status` · docs `140`/`141`/`16`/`33`  
받침: [16](16-sentence-notes.md) · [79](79-shadowing-opt-in.md) · [140](140-mobile-mvp-backlog-split.md)

## 무엇인가

**키보드로 적는** 문장 노트(듣고 적기 · Enter 오버레이)는 제품에서 뺀다.  
**녹음으로 하는 연습**(쉐도잉 등)은 **유지**한다.  
모바일 키보드 노트([141](141-mobile-sentence-notes.md))는 **구현하지 않음 · 후보 삭제**.

| 포함 | 미포함 |
|------|--------|
| 웹: Enter→노트 오버레이 **열지 않음** · UI/Guide 문구 정리 | 쉐도잉·STT 발음 연습 제거 |
| status `sentence_notes_keyboard=false` (기본) | notes/sync·voice API 삭제 (되새김·옛 데이터) |
| 킬로 응급 복구 `ASR_SENTENCE_NOTES_KEYBOARD=1` | 섹션 되새김질 전체 제거 (후속 검토) |
| 141 취소 · 140 목록 갱신 | APK 자체 업데이트 · Live Enable / IPS |

## Product (locked)

1. 키보드 문장 노트 = **없음** (웹 UI 끔 · 앱 141 안 함)  
2. 녹음 연습(쉐도잉) = **유지**  
3. 검증: **폰 + Live** — Enter로 노트 안 열림 · 쉐도잉 진입 경로 존재  
4. fail-closed: 플래그 off일 때 `openNoteOverlay` no-op (성공한 척 열기 금지)

## Kill / rollback

- `ASR_SENTENCE_NOTES_KEYBOARD=1` → status true → 옛 Enter 노트 복구  
- Revert PR · 이전 APK `0.3.57`

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.58**

## Device / E2E pin

- Local `:8768` `/api/status`: `version=0.3.58` · `sentence_notes_keyboard=false`
- Local web: Enter → noteOverlay stays `hidden` · Guide에 Enter/듣고 적기 문구 없음 · `shadowingPracticeCheck` 존재
- Live (pre-CD): still `0.3.57` (no `sentence_notes_keyboard` key) — post-merge CD re-check
- Phone SM-G986N: existing APK path opens (키보드 노트 앱 UI 없음 · 녹음 연습은 웹/기존 경로)
- pytest `tests/test_no_keyboard_sentence_notes.py` · full suite green
- Kill: `ASR_SENTENCE_NOTES_KEYBOARD=1` or revert

Do not paste emails, cookies, tokens, or secrets into chat/PR.
