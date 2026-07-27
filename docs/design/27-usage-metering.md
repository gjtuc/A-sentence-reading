# 27 — 유저별 사용량 · 추정 비용

모듈: `llm/usage_meter.py` · `GET /api/usage` · `GET /api/usage/admin` · 헤더 「사용량」

## 무엇을

운영자(너)가 전액 결제하는 Gemini · Cloud TTS · GCS 사용을 **uid별로 계측**하고,  
공개 단가로 **추정 USD**를 보여 준다. 청구서와 1:1 일치가 아니라 **안내 추정**.

| 보는 사람 | 내용 |
|-----------|------|
| 로그인 유저 | 자기 합계만 |
| 관리자 (`ASR_ADMIN_EMAILS`) | 전체 유저 목록 + 합 |

## 계측

| 항목 | 단위 |
|------|------|
| Gemini | 호출 수 · 입력/출력 문자(또는 usage_metadata 토큰) |
| TTS | 클라우드 합성 문자 수 (캐시 hit 제외) |
| GCS | upload/download 바이트 · op 횟수 |

저장: `users/{uid}/usage.json` (GCS) + 로컬 `data/usage/{uid}.json`

## 추정 단가 (코드 상수 · 변경 가능)

대략 (무료 한도 무시 · USD):

- Gemini 2.5 Flash: in $0.30 / 1M tok · out $2.50 / 1M tok (문자≈토큰 근사)
- TTS Neural2: $16 / 1M chars
- GCS storage 표시는 바이트 합만 (월 저장액은 별도; op 추정 소액)

## API

- `GET /api/usage` — 로그인 필요 · 본인
- `GET /api/usage/admin` — 관리자만

## UI

헤더 **사용량** → 다이얼로그 (본인 추정). 관리자면 전체 표.

## 버전

0.2.24
