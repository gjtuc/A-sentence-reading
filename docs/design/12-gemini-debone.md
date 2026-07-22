# 12 — Gemini sentence debone

모듈: `llm/debone.py` · `llm/env.py`  
키: `Desktop/.cursor/gc_automation.env` 의 `GEMINI_API_KEY` (repo 커밋 금지).  
모델: `ASR_GEMINI_MODEL` (기본 `gemini-2.5-flash`).

## 목표

PDF raw 텍스트에서 저자·인용 조각·각주 번호 등 **비가시 본문(생선 가시)** 을 제거하고  
UI에 구역을 붙여 보여 준다:

`Title: …` · `Abstract: …` · `Introduction: …` · `Results: …` · …

순서: Title → Abstract → Introduction → Methods/Experimental → Results → Discussion → Conclusion.

## 호출

- ingest 시 자동. 문장 1개 = API 1회가 **아님**.
- **1차 survey** (논문 전역 요약) → **2차** raw를 ~5k자 청크로 나눠 청크마다 JSON (맥락 주입).
- 문장 `text`는 plain 또는 **허용 HTML** (`<sub>` `<sup>` `<i>` `<em>`) — 상세 [13-rich-text-two-pass.md](13-rich-text-two-pass.md).
- 진행률: `POST /api/ingest` → `job_id` → `GET /api/ingest/jobs/{id}` 폴링 (`percent`).
- 실패/키 없음 → `split_into_sentences(raw)` 폴백 + `warnings`.

## JSON (청크)

```json
{
  "sentences": [
    {
      "text": "BaZr<sub>0.9</sub>Y<sub>0.1</sub>O<sub>3−δ</sub> shows …",
      "section": "title"|"abstract"|"introduction"|"methods"|"experimental"|"results"|"discussion"|"conclusion"|"body"
    }
  ]
}
```

빈 목록 = 해당 청크 전부 폐기(예: References).

## 상태

`GET /api/status` → `gemini_debone: true|false` (키 존재).  
ingest job 완료 → `debone: true|false`, `warnings: [...]`.
