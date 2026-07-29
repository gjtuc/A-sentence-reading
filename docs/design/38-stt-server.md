# 38 — 서버 STT 발음 연습 (점수 없음)

모듈: `stt/recognize.py` · `POST /api/stt/recognize` · `stt_practice.js` (MediaRecorder)  
받침: [37-stt-browser.md](37-stt-browser.md) compare/diff

## 무엇을

「말하기」가 **서버 인식**을 기본으로 쓴다.

1. 브라우저가 짧게 녹음 (MediaRecorder)
2. 오디오를 `POST /api/stt/recognize` 로 업로드
3. Gemini가 영어 음성 → 글자
4. 기존 `/api/stt/compare` 로 원문과 diff (점수 없음)

브라우저 Web Speech는 **폴백** (서버 불가·Gemini 키 없음·녹음 실패 시).

## 비목표 (이번)

- 발음 점수·AI 채점
- Live Enable / IPS (Trading Gate — ASR 밖)
- Flutter
- 장기 오디오 보관·GCS 음성 아카이브 (노트 voice와 별개)
- 실시간 스트리밍 STT

## API

`POST /api/stt/recognize` (multipart)

| 필드 | 필수 | 설명 |
|------|------|------|
| `file` | yes | 오디오 바이트 (`audio/webm` · `wav` · `mp4` · `ogg` · `mpeg` 등) |
| `expected` | no | 원문 — 있으면 응답에 `compare` 포함 |

성공:

```json
{
  "ok": true,
  "heard": "...",
  "engine": "gemini",
  "compare": { "ok": true, "diff": [ ... ] }
}
```

`expected` 비면 `compare` 생략.

실패: `empty_audio` · `too_large` (>2 MiB) · `unsupported_mime` · `gemini_unavailable` · `recognize_failed`

**INVARIANT:** `score` / `grade` / `accuracy` 없음.

## 한도

| 항목 | 값 |
|------|-----|
| 최대 업로드 | 2 MiB |
| 언어 | 영어 전사 (연습 문장과 동일) |

## UI

- 「말하기」토글: 녹음 중 → 다시 누르면 중지·업로드·인식
- 상태: 「녹음 중…」→「서버 인식 중…」→ diff
- `/api/status.stt_server` 가 false면 브라우저 STT(37)로 폴백
- 문장 변경 시 녹음·패널 초기화 (37과 동일)

## Prefs

`asr.stt.v1` / `.{uid}`: `{ "mode": "server" | "browser" }`  
기본: 서버 가능하면 `server`, 아니면 `browser`.  
(이번 UI에 모드 선택기 없음 — status·prefs만)

## 불변

- INVARIANT: 채점 숫자 없음
- INVARIANT: 읽기 인덱스 불변
- INVARIANT: 노트 MediaRecorder GCS voice와 경로 분리 (`/api/stt/recognize` vs `/api/voice/blobs`)

## 버전

0.2.46
