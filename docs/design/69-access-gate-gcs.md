# 69 — Access gate durable store (GCS)

모듈: `llm/access_gate.py` · `api` lifespan · status `access_gate_gcs`  
받침: [67-access-gate.md](67-access-gate.md) · [22-google-auth-gcs.md](22-google-auth-gcs.md) · [25-cloud-run.md](25-cloud-run.md)

## 무엇을

Cloud Run 등 **에페메랄 디스크·다 인스턴스**에서도 초대·허용·거절이 같은 진실 원본을 보게 한다.

| 로컬 (기존) | GCS (공유 진실) |
|-------------|-----------------|
| `data/auth/invite_codes.json` | `{prefix}/auth/invite_codes.json` |
| `data/auth/access_events.json` | `{prefix}/auth/access_events.json` |
| `data/auth/redeem_attempts.json` | `{prefix}/auth/redeem_attempts.json` |
| `data/auth/accounts.json` (access 필드) | 기존 `{prefix}/auth/accounts.json` (이미 push) |

`accounts.json` 의 `users.*.access` 는 이미 write 시 GCS push 됨.  
이번 칩은 **초대·이벤트·redeem 한도**를 같은 패턴으로 올리고, mint/redeem/decide 전에 pull·merge 한다.

## 왜 선행인가

게이트가 인스턴스 로컬에만 있으면:

- A 인스턴스에서 mint한 OTP가 B에서 `bad_code`
- A에서 Allow 해도 B는 계속 `pending` → 유료 API 403 또는 반대로 빈 성공
- 공유 베타에서 **남의 허용 상태·초대 풀이 섞이거나 유실**

## 동작

1. **write**: 로컬 저장 후 GCS upload (fail-soft — 로컬은 유지, 로그 warning)
2. **refresh** (`refresh_access_gate_from_gcs`): accounts pull + 세 파일 download·merge·로컬 반영
3. **호출 시점**: 서버 lifespan · `mint` · `redeem` · `decide` · `list_pending` · `list_events` · `user_may_use_paid` 직전
4. **merge**:  
   - invites: 같은 `hash`면 status 순위 `redeemed > revoked > revoked > open`  
   - events: `(ts,type,uid,message)` dedupe 후 최근 500  
   - redeem_attempts: uid별 timestamp 합집합·윈도 prune

평문 OTP는 GCS에 **절대** 넣지 않는다 (hash only — 67 불변).

## 비목표

- Live Enable / IPS (Trading Gate — ASR 밖)
- Flutter UI 변경
- BYOK
- GCS 없으면(로컬 only) 기존 디스크 동작 유지

## 킬스위치·롤백

- `ASR_GCS_BUCKET` 비우면 push/pull skip → 로컬 only (단일 프로세스 개발용)
- 문제 시 revert PR 또는 임시로 게이트 `ASR_ACCESS_GATE=0` (비용 보호 약화 — 공유 중엔 비권장)

## status

`access_gate_gcs: true` · version **0.2.87**

## 합격

- GCS 켠 환경: mint 후 `{prefix}/auth/invite_codes.json` 존재 (hash만)
- 두 신원: mint(A) → redeem(B) → allow(A) → B `can_use_paid` (refresh 후)
- GCS 끄면 단위 테스트·로컬 디스크 경로 회귀 OK
- 비밀·평문 OTP가 로그/PR/docs에 없음

## Device E2E (0.2.86 · Samsung sideload)

Against live Cloud Run `version=0.2.86` · `access_gate_gcs=true` (APK may lag; API path is the contract):

1. App opens → bottom tabs (보관·읽기·설정) when session present
2. **설정** → 계정 provider 표시 · `상태: allowed · 유료 API 가능` · admin chrome (OTP 발급 / pending / Allow·Deny) only if admin
3. **새로고침** → status stays coherent (no success-fake empty; paid flag unchanged when still allowed)
4. **로그아웃** → login-only shell (Google/Kakao/email); no prior email, no access status, no pending queue, no minted OTP
5. Unauthenticated `GET /api/access/admin/pending` → **403**; `GET /api/access/status` → `can_use_paid=false` · `status=none`

Do not paste OTP plaintext, emails, or session cookies into chat/PR.

Live Enable / IPS: Trading Gate only (ASR out) — unchanged.
