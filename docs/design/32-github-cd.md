# 32 — GitHub CI · Cloud Run CD

모듈: `.github/workflows/ci.yml` · `deploy-cloud-run.yml` · `deploy_cloud_run.sh` · `check_github_cd_ready.py` · `ensure_github_deploy_sa.sh` · `sync_github_cd_secrets.sh`

## 무엇을

1. **CI** — PR·`main` 푸시마다 `pytest` (항상).
2. **CD** — `main` 푸시(경로 필터) 또는 Actions **Run workflow** 로 Cloud Run 재배포.
3. **Secrets 동기화** — 로컬 `gc_automation.env` + 배포 SA JSON → `gh secret set` (값 미출력).

## 비목표

- Live Enable / IPS (주식 Trading Gate — ASR 범위 밖)
- SA JSON을 Dockerfile·이미지·git 에 굽기 (**금지** — `Desktop/.cursor/secrets/` 만)
- 이 PC 카카오 브라우저 로그인 확인 (차단 환경)

## 불변

- INVARIANT: 배포 자격은 GitHub Secrets — 레포에 키 없음
- INVARIANT: 카카오 REST+Client Secret 함께 유지 또는 둘 다 생략
- INVARIANT: 배포 SA(`asr-github-deploy`) ≠ 런타임 SA(`asr-tts`)

## 켜는 법 (이 PC · 1회)

```bash
export PATH="/c/Users/user/Desktop/.cursor/tools/gcloud-sdk/google-cloud-sdk/bin:$PATH"
export CLOUDSDK_PYTHON="/c/Users/user/Desktop/.cursor/A-sentence-reading/venv/Scripts/python.exe"
cd "/c/Users/user/Desktop/.cursor/A-sentence-reading"

bash scripts/ensure_github_deploy_sa.sh
bash scripts/sync_github_cd_secrets.sh --enable
python scripts/check_github_cd_ready.py   # ok:true · cd_enabled:true
```

### Repository variables / secrets

| 종류 | 이름 |
|------|------|
| var | `ASR_CD_ENABLED=1` · `GCP_PROJECT_ID` · `ASR_CLOUD_RUN_*` · `ASR_GCS_BUCKET` · `ASR_CLOUD_RUN_URL` |
| secret | `GCP_SA_KEY` · `ASR_GOOGLE_CLIENT_ID` · `ASR_AUTH_SECRET` · `GEMINI_API_KEY` · `ASR_KAKAO_*` · `ASR_ADMIN_EMAILS` |

배포 SA 역할: Run Admin, Cloud Build Editor, Artifact Registry Writer, Storage Admin, Service Usage Consumer, runtime SA 에 Service Account User.  
CD 배포는 `ASR_CD_SKIP_API_ENABLE=1` — **`gcloud services enable` 생략** (배포 SA에 API enable 권한 없음).

## 합격

- `check_github_cd_ready.py` → `ok: true`, `cd_enabled: true`, `kakao: on`
- `ASR_CD_DRY_RUN=1` sync: SA JSON 없으면 exit 2
- 레포에 `asr-github-deploy.json` 없음
- Actions Deploy 성공 후 라이브 `/api/status` `version` = 앱 버전

## 운영 기록

| 날짜 | 내용 |
|------|------|
| 2026-07-27 | 수동 배포 0.2.33 · 카카오 env |
| 2026-07-28 | 0.2.34 env-vars-file · 카카오 wipe 방지 |
| 2026-07-28 | CD Secrets · `ASR_CD_ENABLED=1` (0.2.35) |
| 2026-07-28 | 첫 `workflow_dispatch` 실패 — API enable 권한 없음 → **0.2.36** skip enable |
| 2026-07-28 | **CD 성공** — PR #40 merge push deploy · 라이브 `/api/status` **0.2.36** · `kakao: true` |

## 버전

0.2.88 (앱; CD 게이트 자체는 0.2.33–0.2.36)
