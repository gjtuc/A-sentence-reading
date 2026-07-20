# 09 — Testing

## 피라미드

| 층 | 도구 | 대상 |
|----|------|------|
| 단위 | pytest | `sentences`, `PaperSession` 인덱스 불변조건 |
| 계약 | pytest + httpx/TestClient | API 스키마·에러 코드 |
| 수동 | 브라우저 | Immersive 감각·키보드 |

## 필수 테스트 (M2 직전·직후)

1. `test_advance_figure_does_not_move_sentence`
2. `test_advance_sentence_does_not_move_figure`
3. `test_abbrev_fixtures` — [03](03-sentence-split.md) 표
4. `test_status_ok`
5. `test_ingest_not_implemented_or_success` — 단계에 따라

## 픽스처 위치

```
tests/
  test_models_nav.py
  test_sentences.py
  test_api.py
  fixtures/
    text/abbrev_cases.jsonl
    pdfs/   # 작은 합성만 커밋
```

## CI

GitHub Actions는 M2 이후. 1차는 로컬 `pytest`만.

## 수동 체크리스트 (M4)

- [ ] PDF 업로드 → 문장 넘김
- [ ] Shift로 그림만 이동, 문장 번호 유지
- [ ] 그림 없는 PDF empty 안내
- [ ] 50MB+ 거부 메시지
- [ ] 세션 만료 후 404 → 재업로드 안내
