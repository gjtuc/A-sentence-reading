# 86 — Live SMTP wiring (magic-link mail path)

Modules: `email_smtp.py` · `/api/status` · `deploy_cloud_run.sh` · Deploy Cloud Run workflow · sync secrets  
받침: [77](77-email-magic-link.md) · [85](85-web-magic-link-only.md) · [32](32-github-cd.md)

## 무엇인가

라이브에서 매직링크 **실메일 발송**이 되려면 Cloud Run에 `ASR_SMTP_*`가 있어야 한다.  
조사 결과(0.3.2): request → `smtp_not_configured` · GitHub Secrets에 SMTP 키 **없음** · CD env에 SMTP **미전달**.

이번 칩은 **실메일 E2E 자체가 아니라**, 그 선행인 **배선·관측**만 한다.

| 포함 | 미포함 |
|------|--------|
| status `email_smtp_configured` (bool only) | 시크릿 값을 채팅/PR에 넣기 |
| CD·deploy에 optional `ASR_SMTP_*` 전달 | 사용자가 아직 안 넣은 SMTP 계정 만들기 |
| 메일 본문: 웹/앱 로그인 문구 (85) | 실메일 수신 E2E (시크릿 설정 후 다음 칩) |
| docs: 시크릿 이름·설정 방법 (값 예시 REDACTED) | Live Enable / IPS |

## Product

1. SMTP 없으면 request는 계속 503 fail-closed (보낸 척 금지)  
2. status로 “메일 발송 준비됨?”을 **비밀 없이** 볼 수 있음  
3. GitHub Secret을 넣으면 다음 배포부터 Cloud Run에 전달  

## Kill / rollback

- SMTP 시크릿 비우거나 unset → 다음 배포 후 `email_smtp_configured=false` · request 503  
- `ASR_EMAIL_MAGIC_LINK=0` → 매직링크 전체 off  
- Revert PR  

## Version

**0.3.3** · pubspec `0.3.3+1`

## Live Enable / IPS

이번 칩에서 불필요함.

## Ops (after merge — values never in chat/PR)

Set GitHub Actions secrets (stdin / `gh secret set`, not pasted into issues):

- `ASR_SMTP_HOST` · `ASR_SMTP_FROM` (required together)
- `ASR_SMTP_USER` · `ASR_SMTP_PASS` (usually required by provider)
- `ASR_SMTP_PORT` (optional, default 587) · `ASR_SMTP_SSL` (optional)

Example names only: host=`smtp.REDACTED.example`, from=`noreply@REDACTED.example`.

Then redeploy (push to main or workflow_dispatch). Confirm live `/api/status` → `email_smtp_configured=true` before real-mail E2E.

## Live pin (post-merge)

- Cloud Run `/api/status`: `version=0.3.3` · `email_smtp_configured=true` · `mobile_email_magic_link=true` (rev `asr-sentence-reading-00089-*`, 2026-08-11)
- GitHub Actions secrets `ASR_SMTP_HOST` / `_FROM` / `_USER` / `_PASS` / `_PORT` set (values never in chat/PR)
- Live USER/PASS prefer Secret Manager `st-auth-smtp-user` / `st-auth-smtp-password` (runtime SA accessor)
- Next: real-mail magic-link E2E (inbox → open → session)
- Kill: omit SMTP secrets · or `ASR_EMAIL_MAGIC_LINK=0` · revert PR #123

Do not paste SMTP passwords, magic URLs, or real mailboxes into chat/PR.
