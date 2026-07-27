# 32 — GitHub CI · Cloud Run CD

모듈: `.github/workflows/ci.yml` · `deploy-cloud-run.yml` · `scripts/deploy_cloud_run.sh`

## 무엇을

1. **CI** — PR·`main` 푸시마다 `pytest` (항상).
2. **CD** — `main` 푸시(경로 필터) 또는 Actions **Run workflow** 로 Cloud Run 재배포.
   - 기본 **꺼짐** (`vars.ASR_CD_ENABLED` ≠ `1`).
   - 켜면 Secrets로 gcloud 인증 후 기존 `deploy_cloud_run.sh` 호출.

## 비목표

- 카카오 콘솔 키 등록 ([23](23-multi-auth-link.md) — 별도 턴)
- Live Enable / IPS (주식 Trading Gate — ASR 범위 밖)
- SA JSON을 Dockerfile·이미지에 굽기 (**금지**)

## 불변

- INVARIANT: 기기 신뢰 없음 — 세션·UID · GCS 칸만
- INVARIANT: 배포 자격은 GitHub Secrets / Workload Identity — 레포 파일에 키 없음
- Cloud Run 디스크 휘발 — GCS가 진실 ([25](25-cloud-run.md))

## 켜는 법 (1회)

### Repository variables

| 이름 | 값 | 필수 |
|------|-----|------|
| `ASR_CD_ENABLED` | `1` | CD 켜기 |
| `GCP_PROJECT_ID` | `peaceful-basis-503207-t4` | 기본값 있음 |
| `ASR_CLOUD_RUN_REGION` | `asia-northeast3` | 기본값 있음 |
| `ASR_CLOUD_RUN_SERVICE` | `asr-sentence-reading` | 기본값 있음 |
| `ASR_GCS_BUCKET` | `asr-chaheon-warehouse` | 기본값 있음 |

### Repository secrets

| 이름 | 의미 |
|------|------|
| `GCP_SA_KEY` | 배포용 SA JSON (Run Admin + Cloud Build 제출 권한; 런타임 SA와 달라도 됨) |
| `ASR_GOOGLE_CLIENT_ID` | GIS 클라이언트 |
| `ASR_AUTH_SECRET` | 세션 서명 |
| `GEMINI_API_KEY` | 디본·vision |
| `ASR_ADMIN_EMAILS` | (선택) 관리자 이메일 |

배포 SA 최소 역할 예: Cloud Run Admin, Service Account User (런타임 SA), Cloud Build Editor, Storage(아티팩트).

### 로컬 dry-run

```bash
ASR_CD_DRY_RUN=1 ASR_GOOGLE_CLIENT_ID=x ASR_AUTH_SECRET=y GEMINI_API_KEY=z \
  bash scripts/deploy_cloud_run.sh
```

## 합격

- PR에서 CI `pytest` 초록
- `ASR_CD_ENABLED` 미설정 시 Deploy workflow job **skipped** (실패 아님)
- `ASR_CD_ENABLED=1` + secrets 후 `workflow_dispatch` → `/api/status` version 갱신
- 레포·이미지에 `GCP_SA_KEY` / `GEMINI_API_KEY` 평문 없음

## 버전

0.2.33
