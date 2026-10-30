# design/494 — 휴대폰이 받아 가지 않은 서버 논문은 30일 뒤 지운다 (0.3.507)

## 왜

design/185 이후 논문의 주인은 기기다. 휴대폰이 받아 가서 확인(ACK)하면 서버 사본은 바로 지워진다.
남는 것은 휴대폰이 한 번도 받아 가지 않은 사본뿐이다 (웹만 쓴 논문, 분석만 하고 잊은 논문).

design/144 의 90일 만기는 서버 부하를 막으려고 만들었지만 세 군데가 고장 나 있었다.

- 지우기가 목록을 부를 때만, 인스턴스마다 한 시간에 한 번만 돌았다.
- 그 인스턴스의 로컬 목록만 훑어서, 다른 인스턴스가 저장한 논문은 보지 못했다.
- 72시간 정리 반복 (`_paper_handoff_abandon_loop`) 은 사용자를 정하지 않고 돌았다.
  로그인이 켜진 서버에서는 개인 경로가 비어 아무것도 지우지 못했다.

그리고 기기에 있는 논문에는 만기가 의미가 없는데, 앱에는 "(M/d 만료)", "삭제 N일 전", 경고 아이콘, 연장 창이 보였다.

## 무엇

### 서버

- `paper_handoff.purge_all_owners_once()` — `discover_owner_uids()` 로 모든 사용자를 찾고, 사용자마다 `_with_uid(uid)` 로 묶은 뒤
  - `purge_abandoned_once()` (72시간 받다 만 정리, design/185) 와
  - `purge_unclaimed_once()` (30일 정리) 를 돈다.
- `purge_unclaimed_once()` — 원격 목록을 새로 읽고, `updated_at` (없으면 `created_at`) 이 30일 지난 줄을 `abandon_one(cid, reason="unclaimed_ttl")` 로 지운다.
  - `papers/{id}/` 와 목록 줄만 지운다. 노트·북마크·연습은 남는다 (J20).
  - 휴대폰이 지금 받는 중 (pending, 72시간 안) 이면 건너뛴다.
  - 한 번에 `abandon_purge_batch_limit()` 개까지. dry run 은 `ASR_PAPER_HANDOFF_ABANDON_DRY_RUN`.
- `_paper_handoff_abandon_loop` 는 이제 `purge_all_owners_once` 를 부른다. 증거 `paper_handoff_abandon_purge_tick` 에 `owners`, `unclaimed_examined`, `unclaimed_purged` 가 붙는다.
- design/144 의 90일 만기 (`ASR_PAPER_RETENTION`) 는 기본 꺼짐. `=1` 이면 예전 경고·연장·지우기가 돌아온다.
- `/api/status`: `paper_unclaimed_purge`, `paper_unclaimed_days`.

| env | 기본 | 뜻 |
|---|---|---|
| `ASR_PAPER_UNCLAIMED_PURGE` | `1` | `0` 이면 받아 가지 않은 논문을 지우지 않는다 |
| `ASR_PAPER_UNCLAIMED_DAYS` | `30` | 며칠 뒤 지울지 (1–3650) |
| `ASR_PAPER_RETENTION` | `0` | design/144 90일 만기 |

### 앱

- `PaperEntry` 에서 `expiresAt`, `retention*` 를 뺐다. `timingLine` 은 "보관: …" 만, 부제에서 "삭제 N일 전" 을 뺐다.
- 보관함의 경고 아이콘, `_showRetentionSheet`, `extendRetention`, `extendPaperRetention` 을 지웠다.

## 웹만 쓰는 사람

웹은 받아 간 논문을 브라우저 저장소에 넣지만 ACK 하지 않는다 (design/409). 그래서 30일 뒤 서버 사본은 지워지고 브라우저 사본만 남는다.
브라우저 데이터를 지우면 사라질 수 있다는 경고와 PC 도우미의 두 번째 사본은 다음 작업 (도우미 키트) 에서 붙인다.

## 시험

- `tests/test_design_494_unclaimed_purge.py`
- `tests/test_paper_retention.py` (예전 규칙은 `ASR_PAPER_RETENTION=1` 로 고정, 앱 연장 코드가 없어졌는지)
- `mobile/test/paper_models_test.dart` (보관 줄에 "만료" 없음)
