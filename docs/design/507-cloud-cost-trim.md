# design/507 — 클라우드 비용 줄이기: 서버 최대 2대, 읽어주기 음성 60일 보관 (0.3.518)

## 문제

- 10월 청구 약 41만 원: Cloud Run 약 25만, 읽어주기(TTS) 약 10만(555만 글자), 이미지 저장소 약 5만.
- API는 최대 6대까지 늘었다. 한 사람이 쓰는데 2–6대로 늘어난 시간이 주당 61시간이었다. 인스턴스 기반 과금이라 늘어난 대수는 놀는 15분까지 모두 돈이다.
- 읽어주기 MP3 캐시는 7일 뒤 지워져서, 일주일 뒤 같은 논문을 다시 읽으면 다시 합성비를 냈다.

## 결정

- API `ASR_MAX_INSTANCES` 기본 2 (`ASR_API_MAX_INSTANCES`로 바꿀 수 있다). 동시 16 × 2대 = 32 요청이면 한 사람에게 충분하다.
- 워커 기본 4 → 2. CD 프로필 `turn2-scale-to-zero`도 2.
- `_TTS_CACHE_KEEP_DAYS` 7 → 60. MP3 보관비는 한 달 몇십 원 수준이다.
- 오늘 같이 한 일 (코드 밖): Artifact Registry 정리 정책, run-sources 버킷 7일 수명, GitHub CD 끄기(`ASR_CD_ENABLED=0`), 주식 `st-trading-ui` 2 CPU·8Gi → 1 CPU·2Gi (30일 최대 메모리 0.5GiB, `SYNC_ON_START=0`). 주식 저장소 배포 스크립트는 아직 8Gi라 다음 주식 배포에서 되돌아갈 수 있다.

## 시험

- `tests/test_scale_to_zero_395.py::test_max_instances_default_is_two_507`
- `tests/test_tts_cache_retention.py` — 기본 60일.
