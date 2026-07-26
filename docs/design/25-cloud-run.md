# 25 — Cloud Run 문지기 (PC 꺼도 창고)

모듈: `Dockerfile` · `scripts/deploy_cloud_run.sh` · 세션 쿠키 Secure · Secret/env

## 무엇을

로컬 `127.0.0.1:8770` 문지기를 **항상(요청 시) 켜진 Cloud Run**으로 옮긴다.  
창고는 이미 GCS `asr-chaheon-warehouse` · `users/{uid}/…`.  
Run = 로그인 검증 + SA로 GCS/TTS/Gemini 호출.

## 비목표 (이 턴)

- 유저별 추정 비용 UI ([나중 턴](17-rumination-revisions.md))
- 카카오 콘솔 키
- GitHub 자동 CD (수동 `gcloud run deploy --source` 먼저)

## 불변

- INVARIANT: 기기 신뢰 없음 — 세션·UID · GCS 칸만
- INVARIANT: SA JSON을 이미지에 넣지 않음 — Run **런타임 SA** + Secret Manager/env
- Cloud Run 디스크는 **임시** — 논문·노트·목소리는 GCS가 진실 (로컬 `data/` 는 휘발)

## 환경 (Run 서비스)

| 이름 | 의미 |
|------|------|
| `PORT` | Cloud Run이 주입 (앱이 이 포트 listen) |
| `ASR_GCS_BUCKET` | `asr-chaheon-warehouse` |
| `ASR_GCS_PREFIX` | `asr` |
| `ASR_GOOGLE_CLIENT_ID` | GIS 클라이언트 ID |
| `ASR_AUTH_SECRET` | 세션 서명 (**강한 랜덤**, 로컬 dev 기본값 금지) |
| `ASR_EMAIL_AUTH` | `1` |
| `GEMINI_API_KEY` | 디본·vision |
| `ASR_COOKIE_SECURE` | `1` (HTTPS 쿠키; Run 기본) |

`GOOGLE_APPLICATION_CREDENTIALS` 파일 **불필요** — Run 서비스 계정 ADC.

## 런타임 SA 역할

서비스 계정 예: 기존 `asr-tts@PROJECT.iam.gserviceaccount.com`

- Storage Object Admin (버킷) — 이미 있음
- Cloud Text-to-Speech User
- (선택) Secret Accessor

## Google 로그인 콘솔 (배포 URL 받은 뒤)

승인된 JavaScript 원본에 추가:

- `https://<service>-<hash>.a.run.app`

## 배포 (이 PC에 Docker 없어도 됨)

Cloud Build가 원격 빌드:

```bash
# 1회: gcloud CLI 설치 · gcloud auth login · project 설정
gcloud config set project peaceful-basis-503207-t4

# API 사용 설정
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

bash scripts/deploy_cloud_run.sh
```

또는 Console → Cloud Run → 소스에서 배포 (Dockerfile 사용).

## 합격

- `https://…run.app/api/status` → `ok` · `gcs.ready` · `version` ≥ 0.2.21  
- PC 꺼도 폰 브라우저로 로그인 · 노트 sync  
- 이미지/로그에 SA JSON·GEMINI 키 없음

## 버전

0.2.21
