# A-sentence-reading

논문 PDF를 **위: 문장 하나**, **아래: 그림 하나**로 쪼개어, 각각 화살표로 넘기며 읽는 리더.

> **제품 경로:** Android 앱(사이드로드 APK) → **Cloud Run (Live)** 만.  
> PC에서 `127.0.0.1` uvicorn을 켜서 쓰는 경로는 **제거됨** ([design/138](docs/design/138-no-local-server-traces.md)).

## 왜 있나

단어를 하나씩 완벽히 잡고 가면 오히려 전체가 안 잡힌다.  
한 문장이 한눈에 들어올 때까지 반복하고, 그림은 본문과 위치가 어긋나므로 **사람이 맞춰 둔다**.

자세한 제품 의도: [docs/PRODUCT.md](docs/PRODUCT.md)

## 목업 (목표 UI)

```
┌─────────────────────────────────────┐
│            한 문 장                   │
│   <   One sentence at a time.   >   │
├─────────────────────────────────────┤
│              그 림                   │
│         <   [ figure ]   >          │
└─────────────────────────────────────┘
```

- 위 문장 / 아래 그림. 네비는 **독립** (자동 Fig↔문장 매칭 없음)
- 스플리터로 아래 그림을 접어 문장 영역을 키울 수 있음
- 문장 패널은 Immersive Reader식 → [docs/UX.md](docs/UX.md)

## 비목표 (지금은 / 의도적으로 안 함)

- AI 요약·챗봇 논문 해석
- “Fig. 1” 언급 → 그림 자동 점프를 제품 핵심으로 강제 (수동 동기화가 기본)
- Azure Immersive Reader SDK 임베드 (룩만 CSS로 재현)
- **로컬 PC 서버를 켜서 앱/웹을 붙이는 사용** (design/138)

## Live (유일한 운영 경로)

웹·API:

`https://asr-sentence-reading-984608876300.asia-northeast3.run.app`

상태: `/api/status`  
모바일: [`mobile/`](mobile/) — Flutter · [design/33](docs/design/33-mobile-flutter.md)  
CD: [design/32](docs/design/32-github-cd.md) · `ASR_CD_ENABLED=1`

옛 Windows 「Ensure Server」 스케줄러가 남아 있으면:

```bash
./venv/Scripts/python.exe -m sentence_reading.autostart unregister
```

`register` / `ensure` 는 **거부**됩니다 (로컬 uvicorn을 다시 켜지 않음).

## 문서

| 문서 | 내용 |
|------|------|
| [docs/PRODUCT.md](docs/PRODUCT.md) | 읽기 방법·수동 동기화 |
| [docs/UX.md](docs/UX.md) | 레이아웃·타이포·키보드 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 모듈·데이터 흐름 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Immersive Reader·유사 제품 |
| [docs/COMMENTING.md](docs/COMMENTING.md) | `# WHY:` 주석 규칙 |
| [docs/design/](docs/design/README.md) | **구현용 쪼개진 설계** |
| [docs/design/25-cloud-run.md](docs/design/25-cloud-run.md) | Cloud Run 문지기 |
| [docs/design/32-github-cd.md](docs/design/32-github-cd.md) | GitHub pytest CI · Cloud Run CD |
| [docs/design/138-no-local-server-traces.md](docs/design/138-no-local-server-traces.md) | 로컬 서버 흔적 제거 |

## 스택

Python 3.11+ · FastAPI · Vanilla HTML/CSS/JS · Flutter (Android) · PyMuPDF · Gemini · GCS

## 라이선스

아직 미정. 개인/연구용으로 시작.
