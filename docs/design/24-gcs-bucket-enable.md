# 24 — GCS 버킷 실연결

모듈: `llm/gcs_sync.py` · `gc_automation.env` · SA `asr-tts@…`

## 무엇을

로그인 UID 칸(`users/{uid}/…`)·노트·목소리·논문 캐시·TTS 캐시가 **실제로** 버킷에 쓰이게 한다.  
코드·경로 계약은 0.2.9–0.2.18에 있음. 이 문서는 **운영 켜기**다.

## 왜 지금

- Google 로그인 OK여도 `ASR_GCS_BUCKET` 없으면 sync off
- TTS용 SA(`GOOGLE_APPLICATION_CREDENTIALS`)에 **해당 버킷 object 권한**이 필요

## 콘솔 (사람 1회)

1. [Cloud Console → 스토리지](https://console.cloud.google.com/storage) · 프로젝트 `peaceful-basis-503207-t4`
2. **버킷 만들기** — 이름 전역 유일 (예: `asr-chaheon-warehouse`)
3. 위치: 가까운 리전 · 접근제어: **균일(버킷 수준)** 권장
4. 버킷 → **권한** → 주 구성원 추가  
   - 주 구성원: `asr-tts@peaceful-basis-503207-t4.iam.gserviceaccount.com`  
   - 역할: **Storage Object Admin** (`roles/storage.objectAdmin`)  
   (버킷 생성·목록은 사람 계정; SA는 object만 있어도 sync 가능)
5. `gc_automation.env`  
   `ASR_GCS_BUCKET=<버킷이름>`  
   `ASR_GCS_PREFIX=asr` (기본)

## 합격

- `GET /api/status` → `gcs.enabled` · `gcs.ready` true  
- 로그인 후 `gcs.notes_object` 가 `asr/users/{uid}/notes/…`  
- 노트 저장 → GCS에 object 생김 (다른 PC·같은 계정 pull)

## 운영 기록 (이 PC)

| | |
|--|--|
| 버킷 | `asr-chaheon-warehouse` |
| 리전 | `asia-northeast3` (서울) |
| SA | `asr-tts@peaceful-basis-503207-t4.iam.gserviceaccount.com` · Storage Object Admin |
| env | `ASR_GCS_BUCKET` · `ASR_GCS_PREFIX=asr` (`gc_automation.env`) |
| smoke | `asr/auth/_smoke_probe.txt` upload/download OK (2026-07-26) |

다음: Cloud Run에 문지기 배포 (PC 꺼도 동일 창고).

## 버전

0.2.20 — 버킷 실연결 + Google 로그인 이중 버튼 제거(prompt).
