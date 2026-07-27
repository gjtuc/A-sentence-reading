# 32 — GitHub CI · Cloud Run CD

모듈: `.github/workflows/ci.yml` · `deploy-cloud-run.yml` · `scripts/deploy_cloud_run.sh` · `check_github_cd_ready.py`

## 무엇을

1. **CI** — PR·`main` 푸시마다 `pytest` (항상).
2. **CD** — `main` 푸시(경로 필터) 또는 Actions **Run workflow** 로 Cloud Run 재배포.
   - 기본 **꺼짐** (`vars.ASR_CD_ENABLED` ≠ `1`).
   - 켜면 Secrets로 gcloud 인증 후 `deploy_cloud_run.sh` 호출.
3. **안전** — `gcloud --env-vars-file` 로 환경 일괄 설정. 카카오 키를 빼먹으면 라이브 카카오 로그인이 꺼지므로, 있으면 **둘 다** 넣는다.

## 비목표

- Live Enable / IPS (주식 Trading Gate — ASR 범위 밖)
- SA JSON을 Dockerfile·이미지에 굽기 (**금지**)
- 이 PC에서 카카오 브라우저 로그인 확인 (차단 환경 — 키·Cloud Run `providers.kakao` 만 검증)

## 불변

- INVARIANT: 기기 신뢰 없음 — 세션·UID · GCS 칸만
- INVARIANT: 배포 자격은 GitHub Secrets — 레포 파일에 키 없음
- INVARIANT: CD 배포는 카카오 REST+Client Secret을 **함께** 유지하거나 **둘 다 생략** (partial 금지)
- Cloud Run 디스크 휘발 — GCS가 진실 ([25](25-cloud-run.md))

## 켜는 법 (1회)

사전 점검 (값 출력 없음):

```bash
python scripts/check_github_cd_ready.py
```

### Repository variables

| 이름 | 값 | 필수 |
|------|-----|------|
| `ASR_CD_ENABLED` | `1` | CD 켜기 |
| `GCP_PROJECT_ID` | `peaceful-basis-503207-t4` | 기본값 있음 |
| `ASR_CLOUD_RUN_REGION` | `asia-northeast3` | 기본값 있음 |
| `ASR_CLOUD_RUN_SERVICE` | `asr-sentence-reading` | 기본값 있음 |
| `ASR_GCS_BUCKET` | `asr-chaheon-warehouse` | 기본값 있음 |
| `ASR_CLOUD_RUN_URL` | 라이브 URL | 기본값 있음 |

### Repository secrets

| 이름 | 의미 |
|------|------|
| `GCP_SA_KEY` | 배포용 SA JSON (Run Admin + Cloud Build 제출; 런타임 `asr-tts` 와 달라도 됨) |
| `ASR_GOOGLE_CLIENT_ID` | GIS 클라이언트 |
| `ASR_AUTH_SECRET` | 세션 서명 |
| `GEMINI_API_KEY` | 디본·vision |
| `ASR_ADMIN_EMAILS` | (선택) 관리자 이메일 |
| `ASR_KAKAO_REST_API_KEY` | (권장) 카카오 REST |
| `ASR_KAKAO_CLIENT_SECRET` | (권장) 카카오 client secret — 콘솔에서 ON 이면 **필수** |

로컬에서 secrets 채우기 예 (`gc_automation.env` source 후):

```bash
gh secret set ASR_GOOGLE_CLIENT_ID --body "$ASR_GOOGLE_CLIENT_ID"
gh secret set ASR_AUTH_SECRET --body "$ASR_AUTH_SECRET"
gh secret set GEMINI_API_KEY --body "$GEMINI_API_KEY"
gh secret set ASR_KAKAO_REST_API_KEY --body "$ASR_KAKAO_REST_API_KEY"
gh secret set ASR_KAKAO_CLIENT_SECRET --body "$ASR_KAKAO_CLIENT_SECRET"
gh secret set GCP_SA_KEY < /path/to/deploy-sa.json
gh variable set ASR_CD_ENABLED --body 1
```

### 로컬 dry-run

```bash
ASR_CD_DRY_RUN=1 ASR_GOOGLE_CLIENT_ID=x ASR_AUTH_SECRET=y GEMINI_API_KEY=z \
  bash scripts/deploy_cloud_run.sh
# kakao=on|off|partial 표시. partial 이면 exit 2
```

## 합격

- PR에서 CI `pytest` 초록
- `ASR_CD_ENABLED` 미설정 시 Deploy workflow job **skipped**
- `check_github_cd_ready.py` → `ok: true` 후 `ASR_CD_ENABLED=1` → `workflow_dispatch`
- 레포·이미지에 SA JSON·API 키 평문 없음
- 재배포 후에도 라이브 `auth.providers.kakao` 유지 (카카오 secrets 넣은 경우)

## 운영 메모

| 날짜 | 내용 |
|------|------|
| 2026-07-27 | 수동 배포 0.2.33 · 카카오 env 수동 update |
| 2026-07-28 | deploy 스크립트가 카카오 키를 env-vars-file에 포함 (0.2.34) — CD wipe 방지 |

카카오 Redirect URI (개편 후): **앱 → 플랫폼 키 → REST API 키 → 카카오 로그인 리다이렉트 URI** ([23](23-multi-auth-link.md)).

## 버전

0.2.34
