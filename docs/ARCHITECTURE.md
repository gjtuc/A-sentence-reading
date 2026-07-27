# Architecture

## 목표

PDF → (figures[], sentences[]) → UI.  
UI에서 그림·문장 인덱스는 **독립**으로만 움직인다.

```mermaid
flowchart TB
  pdf[PDF_upload] --> extract[pdf.extract]
  extract --> figs[figures_list]
  extract --> text[raw_text]
  text --> split[pdf.sentences]
  split --> sents[sentences_list]
  figs --> session[PaperSession]
  sents --> session
  session --> api[FastAPI]
  api --> uiTop[Figure_carousel]
  api --> uiBot[One_sentence_panel]
  uiTop -.->|manual_sync| human[Human]
  uiBot -.->|manual_sync| human
```

## 디렉터리

```
src/sentence_reading/
  models.py          # Figure, Sentence, PaperSession
  pdf/
    extract.py       # figures + text from PDF (stub)
    sentences.py     # split_into_sentences (stub)
  api/
    app.py           # HTTP + static
  static/
    index.html
    styles.css
    app.js
```

## 모듈 책임

| 모듈 | 책임 | 비책임 |
|------|------|--------|
| `models` | 데이터 형태·인덱스 불변조건 문서화 | I/O, UI |
| `pdf.extract` | PDF 바이트 → 그림 바이너리/메타 + 원문 텍스트 | 문장 분할, HTTP |
| `pdf.sentences` | 원문 → 문장 리스트 | PDF 파싱 |
| `api.app` | 라우팅, 정적 파일, ingest 자리 | 비즈니스 로직 본문 |
| `static/*` | 표시·네비·타이포 | PDF 알고리즘 |

## API (스켈레톤)

| Method | Path | 동작 |
|--------|------|------|
| GET | `/` | `index.html` |
| GET | `/api/status` | `{ ok, stage: "skeleton", pdf_extract: false }` |
| GET | `/api/session/mock` | mock figures + sentences (UI 데모) |
| POST | `/api/ingest` | stub → 501 또는 “not implemented” JSON |

## PaperSession 불변조건

- `figure_index ∈ [0, len(figures))` (비어 있으면 UI가 empty 상태)
- `sentence_index ∈ [0, len(sentences))`
- `advance_figure(±1)` 는 `sentence_index`를 바꾸지 않는다
- `advance_sentence(±1)` 는 `figure_index`를 바꾸지 않는다

이 불변조건이 깨지면 제품 가설(수동 동기화)이 깨진다.

## 배포 · CI/CD (0.2.33)

| 경로 | 역할 |
|------|------|
| 로컬 `127.0.0.1:8770` | 개발 문지기 |
| Cloud Run | PC 꺼도 동일 API · GCS 창고 ([design/25](design/25-cloud-run.md)) |
| `.github/workflows/ci.yml` | PR·`main` 마다 pytest (**항상**) |
| `.github/workflows/deploy-cloud-run.yml` | Cloud Run 재배포 (**기본 off**) |

CD를 켜려면 GitHub repository variable `ASR_CD_ENABLED=1` 과 Secrets(`GCP_SA_KEY`, `ASR_GOOGLE_CLIENT_ID`, `ASR_AUTH_SECRET`, `GEMINI_API_KEY`) — 상세 [design/32](design/32-github-cd.md).  
이미지·레포에 SA JSON·API 키를 넣지 않는다. 런타임은 Cloud Run ADC.

## 구현 순서 (권위: design/)

세부는 **[design/](design/README.md)** 가 권위 문서다. M0–M5·reading-order·CI/CD 게이트까지 반영됨.  
남은 운영: 카카오 콘솔 키 · `ASR_CD_ENABLED` 실켜기 1회.

에러·한도·테스트: [08](design/08-errors.md) · [09](design/09-testing.md) · [10](design/10-security-limits.md)
