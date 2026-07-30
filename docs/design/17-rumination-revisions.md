# 17 — Rumination revisions (텍스트 append-only + 섹션 분기 리뷰)

모듈: `static/notes_revisions.js` · `static/app.js` · `static/index.html`  
저장: `localStorage` `asr.notes.v2` (v1 자동 이관)

## 제품 정의

- 훈련의 목적은 **내가 쓴 글(·목소리)을 되새김질**하는 것. 논문 문장은 자극.
- 문장마다 기록을 **전부 보관**, 기본 UI는 **최신 rev만**.
- 섹션(분기)이 바뀔 때(다음 섹션으로 전진) 직전 섹션의 최신 기록들을 엮어 **분기 리뷰**.
- 리뷰에서 문장을 고르면 다시 쓰고 **새 rev를 append** (이전 rev 삭제 없음).

## 불변조건

- INVARIANT: 리뷰·노트는 AI 채점 없음.
- INVARIANT: 그림/문장 인덱스 독립 — 리뷰가 인덱스를 바꿀 때는 **사용자가 문장을 고른 경우만**.
- INVARIANT: 저장은 append-only. “복원”도 새 rev.

## 스키마 v2

```json
{
  "version": 2,
  "papers": {
    "<paperKey>": {
      "<sentenceId>": {
        "text": [{ "rev": 1, "at": "ISO-8601", "body": "…" }],
        "voice": []
      }
    }
  }
}
```

- `paperKey`: `cache:` / `ses:` / `id:` (기존과 동일)
- 타이핑 중 debounce는 **메모리 draft만**; disk append는 닫기·문장 이동·리뷰 저장 시

## 섹션 경계

- `advanceSentence(+1)` 에서 `prev.section !== next.section` 이면 직전 섹션 리뷰 오픈
- 뒤로 가기(`-1`)에서는 리뷰 안 띄움
- 리뷰 행: ~~글 영역 클릭 → 문장 선택~~ → **0.2.59** 부터 구간 노트를 **한 박스에 이어 보기** ([51](51-section-review-flow.md)); **0.2.60** **▶ 이어 듣기** ([52](52-section-review-voice-seq.md)); 헤더「되새김」on/off ([53](53-section-review-optional.md) · 0.2.61); 일시 정지 클립 재듣기/재녹음 ([54](54-section-review-voice-clip.md) · 0.2.62); 콕 수정은 후속 (인덱스 불변)
- 리뷰 닫기·TTS·다른 목소리 재생 시 이전 목소리 중단

## 다음

- ~~Signalsmith WASM으로 `tts_stretch.js` 교체~~ (0.2.7 — vendored 1.3.2, 폴백 preservesPitch)
- ~~분기 리뷰 목록에 최신 목소리 재생 버튼~~ (0.2.8)
- ~~GCS TTS 캐시 upload/download~~ (0.2.9 — `ASR_GCS_BUCKET` · `llm/gcs_sync.py`)
- ~~GCS 노트 store sync~~ (0.2.10 — `GET|PUT /api/notes/sync` · `{prefix}/notes/store_v2.json`)
- ~~GCS voice blob sync~~ (0.2.11 — `GET|PUT /api/voice/blobs` · `{prefix}/voice/{sha256}.bin`)
- ~~GCS 논문 캐시(session+figures) sync~~ (0.2.12 — 원본 PDF 제외 · `cache_id` 유지)
- ~~보관 목록 UI~~ (0.2.13 — [18-paper-library.md](18-paper-library.md))
- ~~보관 목록에서 삭제~~ (0.2.14 — 로컬+GCS)
- ~~pipeline_version stale 정책~~ (0.2.15 — [19-pipeline-cache.md](19-pipeline-cache.md))
- ~~원본 PDF/DOCX 백업·재분석~~ (0.2.16 — [20-source-backup.md](20-source-backup.md))
- ~~진행(문장·그림 인덱스) 복원~~ (0.2.17 — [21-progress-restore.md](21-progress-restore.md))
- ~~Google 로그인 · UID별 GCS 칸~~ (0.2.18 — [22-google-auth-gcs.md](22-google-auth-gcs.md))
- ~~카카오·이메일 · 계정 연결~~ (0.2.19 — [23-multi-auth-link.md](23-multi-auth-link.md))
- ~~GCS 버킷 실연결~~ (0.2.20 — [24-gcs-bucket-enable.md](24-gcs-bucket-enable.md))
- ~~Cloud Run 문지기 스캐폴드~~ (0.2.21 — [25-cloud-run.md](25-cloud-run.md))
- ~~Cloud Run 실배포 · ADC~~ (0.2.22)
- ~~Cloud Run Google OAuth 원본~~ (0.2.23 — [26-cloud-run-oauth-origin.md](26-cloud-run-oauth-origin.md))
- ~~유저별 사용량·추정 비용 UI~~ (0.2.24 — [27-usage-metering.md](27-usage-metering.md))
- ~~Fig. N → 그림 점프 힌트~~ (0.2.25 — [28-fig-ref-jump.md](28-fig-ref-jump.md))
- ~~Compound figure (1a/1b) 분해~~ (0.2.26 — [29-compound-figures.md](29-compound-figures.md))
- ~~음절·품사 색~~ — **하지 않음** (0.2.30 원복 · RESEARCH 비목표)
- ~~다단 reading-order~~ (0.2.32 — [31-reading-order.md](31-reading-order.md))
- ~~GitHub CI · Cloud Run CD~~ (0.2.33 — [32-github-cd.md](32-github-cd.md))

다음 운영: (선택) Actions `workflow_dispatch` 로 라이브 0.2.35 반영.

라이브 카카오: Cloud Run env 반영됨 · 이 PC 브라우저 확인은 건너뜀.
CD: Secrets 동기화 · `ASR_CD_ENABLED=1` (0.2.35 — [32](32-github-cd.md)).

## GCS

| env | 의미 |
|-----|------|
| `ASR_GCS_BUCKET` | 버킷 (비우면 sync off) |
| `ASR_GCS_PREFIX` | prefix (기본 `asr`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | SA JSON (TTS와 공유) |

**TTS 캐시:** 로컬 → GCS get → Cloud 합성 → 로컬+GCS put.  
object: `{prefix}/tts_cache/{sha24}.mp3`

**노트 store:** 부팅 시 pull · 저장 후 debounce push.  
병합: fingerprint(`at`+`body` / `at`+`blobKey`) 합집합 → `at` 정렬 → `rev` 재번호 (삭제 없음).  
object: `{prefix}/notes/store_v2.json` · 한도 2MB.

**Voice blob:** 녹음 직후 PUT · 재생 시 IDB miss → GET → IDB 채움.  
object: `{prefix}/voice/{sha256(blobKey)}.bin` · 한도 5MB.  
blobKey 문자열은 노트 JSON에 그대로 두고, GCS 경로만 해시.

**논문 캐시:** 분석 저장 시 push · ingest 제목 매칭 miss 시 remote index pull · `/open` 로컬 miss 시 pull.  
object: `{prefix}/papers/index.json` · `{prefix}/papers/{cache_id}/session.json` · `…/figures/*` · `…/source.pdf|docx`(있을 때).  
`cache_id` 안정 → 노트 키 `cache:{id}` 유지. 재분석: [20-source-backup.md](20-source-backup.md).