# A-sentence-reading

논문 PDF를 **위: 문장 하나**, **아래: 그림 하나**로 쪼개어, 각각 화살표로 넘기며 읽는 로컬 리더.

> 현재 단계: **가이드 + 주석 스켈레톤**. mock UI는 동작하고, 실제 PDF 파싱은 아직 stub입니다.

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
- “Fig. 1” 언급 → 그림 자동 점프 (수동 동기화가 제품 핵심)
- Azure Immersive Reader SDK 임베드 (룩만 CSS로 재현)

## 로컬 실행 (스켈레톤)

```bash
cd /c/Users/user/Desktop/.cursor/A-sentence-reading
python -m venv venv
./venv/Scripts/python.exe -m pip install -e .
./venv/Scripts/python.exe -m uvicorn sentence_reading.api.app:app --reload --host 127.0.0.1 --port 8770
```

브라우저: [http://127.0.0.1:8770/](http://127.0.0.1:8770/)  
상태: [http://127.0.0.1:8770/api/status](http://127.0.0.1:8770/api/status)

## 문서

| 문서 | 내용 |
|------|------|
| [docs/PRODUCT.md](docs/PRODUCT.md) | 읽기 방법·수동 동기화 |
| [docs/UX.md](docs/UX.md) | 레이아웃·타이포·키보드 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 모듈·데이터 흐름 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Immersive Reader·유사 제품 |
| [docs/COMMENTING.md](docs/COMMENTING.md) | `# WHY:` 주석 규칙 |
| [docs/design/](docs/design/README.md) | **구현용 쪼개진 설계** (마일스톤·데이터·PDF·API·UI 상태·테스트…) |

## 스택

Python 3.11+ · FastAPI · Vanilla HTML/CSS/JS · (다음) PyMuPDF · (다음) pysbd

## 라이선스

아직 미정. 개인/연구용으로 시작.
