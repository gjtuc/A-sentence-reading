# design/383 — 폰이 자기 디스크에서 연 논문

## 문제

design/378 은 논문의 기준 소리를 **읽을 때가 아니라 미리** 짓게 했다. 걸어 둔 자리가 두 곳이었다.

- 분석이 끝나는 자리 (`_finish_job`)
- 논문을 여는 자리 (`POST /api/cache/papers/{id}/open`)

두 번째는 "design/378 이전에 분석한 논문"을 위한 것이었다. 그 논문들은 첫 번째를 못 받았으니 여는 순간이 유일한 기회라고 적었다.

그런데 그 기회가 오지 않는다. design/185 는 **폰에 이미 내려와 있는 논문을 폰 디스크에서 바로 연다.** `/open` 을 아예 부르지 않는다. 그래서 미리 짓기가 가장 필요한 논문 — 예전에 분석해서 이미 폰에 있는 논문 — 이 정확히 그 경로를 안 탄다.

0.3.420 라이브 로그가 그대로 보여 준다.

```
reader_open      stage = local_paper_disk    ingest_status = local
sound_ref_warm   0건
sound_ref_code   queued 2건 / ready 1건
ref_code         queued 3건
```

168문장 논문을 열고 세 문장을 읽었고, 두 문장은 기준 소리가 없어서 읽기 시작한 뒤에 짓기 시작했다. design/378 이 없애려던 그 건너뛰기다.

## 침묵이 더 나쁜 문제였다

`_warm_sound_refs` 는 `load_cached_session` 이 비면 **아무 말 없이 돌아갔다.** 그래서 로그에서

- 폰이 서버에 묻지도 않은 경우
- 물었지만 서버에 그 논문이 없는 경우
- 미리 짓기가 아예 안 걸린 경우

이 셋이 전부 똑같이 "행이 없음" 으로 보였다. 하루를 이걸로 잘못 짚었다.

## 고침

### 서버 — 얇은 주소 하나

`POST /api/cache/papers/{id}/sound-warm`

`/open` 에서 이 일에 필요한 부분만 가져왔다.

1. `_paid_access_denied` — 미리 짓기는 합성 호출을 쓴다. 열린 문이 되면 안 된다.
2. `refresh_paper_for_open` — 이 인스턴스에 논문 사본이 없으면 GCS 에서 당긴다. 이게 없으면 찬 인스턴스에서는 할 일이 없다.
3. `_warm_sound_refs`

번역 백필을 깨우거나 세션을 만들지 않는다. 짓기가 시작되기 **전에** 답하고 이유만 말한다. 폰은 쏘고 걸어간다.

### 서버 — 침묵 없애기

`load_cached_session` 이 비면 `stage=skip`, `warm_miss=no_session` 을 적는다. 주소가 논문을 못 당기면 `warm_miss` 에 그 이유를 적는다.

### 폰

`local_paper_disk` 로 열고 난 뒤 `unawaited(_askSoundWarm(entry.id))`. 답을 `sound_ref_warm` / `stage=ask` / `warm_ask=<code>` 로 적는다.

`askSoundWarm` 은 절대 던지지 않는다. 못 물어본 미리 짓기는 **원래 있던 동작**(읽을 때 짓기)으로 돌아가는 것이고, 논문 여는 것 자체는 막히면 안 된다. 옛 서버의 404 는 `http_404` 라는 글자로만 남는다.

## 안 고친 것

`dispersed` 를 `disperse` 로 읽는 것은 여전히 어떤 식으로도 안 잡힌다 (design/382 참고). 이 문서와 무관하다.

## 로그로 확인하는 법

```bash
python scripts/pull_evidence.py --merge-ops --kind sound_ref_warm --since 1d --limit 200 --out .cache/warm.json
```

| 보이는 것 | 뜻 |
|---|---|
| `stage=ask` `warm_ask=started` | 폰이 물었고 서버가 짓기 시작했다 |
| `stage=ask` `warm_ask=no_paper` | 서버에 그 논문이 없다 |
| `stage=ask` `warm_ask=http_404` | 서버가 이 주소를 모르는 옛 버전이다 |
| `stage=ask` `warm_ask=ask_failed` | 폰이 서버에 못 닿았다 |
| `stage=start` `warm_n=N` | N문장을 걷기 시작했다 |
| `stage=done` `warm_built`/`warm_ready` | 새로 지은 수 / 이미 있던 수 |
| `stage=skip` `warm_miss=...` | 걸을 논문이 없었다 |

행이 아예 없으면 이제는 **폰이 묻지 않은 것**뿐이다.

## 0.3.421 라이부 결과 — 한 층 알래가 더 있었다

### 허용 목록에 없어서 처음부터 버려지고 있었다

`sound_ref_warm` 은 `ops_events._ALLOWED_KINDS` 에도 `evidence_kinds.ALLOWED_KINDS` 에도 없었다. `ops_events.emit` 은 목록에 없는 종류를 **아무 말 없이 `return None`** 한다. 그래서 design/378 을 올린 0.3.418 이후 모든 미리 짓기 행이 버려졌다.

위 표의 「행이 없으면 폰이 묻지 않은 것」 은 **틀렸다.** 행이 없었던 이유는 처음부터 버려지고 있었기 때문이다.

- 고침: `evidence_kinds.ALLOWED_KINDS` 에 넣고, 미리 짓기는 `ops_events` 가 아니라 **증거 버스**로 적는다. 다른 소리 행들이 이미 거기 산다.
- 시험: `test_the_warm_kind_is_allowed_through_the_door`

교훈: 「행이 없다」 를 진단으로 삼기 전에 그 종류가 허용 목록에 있는지 먼저 본다.

### 그 논문은 사버에 사본이 없었다

폰은 주소를 제대로 부랐다 (Cloud Run `200`, `11:55:44`). 그런데 같은 초에 `download_cache_fail reason=session_missing` 이 찍혔다. `7d506b60fb6b` 은 **폰에만 있는 논문**이고 GCS 에 사본이 없다. 그게 예전에 분석한 논문의 모양이다 — cache_id 만 보내는 설계는 정확힐 필요한 논문에서 못 쓴다.

- 고침: 폰이 **자기가 가진 문장 글자를 같이 보낸다** (`{"texts": [...]}`). 기준 소리는 문장마다 한 개이고 논문에 매달리지 않으니, 논문은 필요 없고 문장이면 충분하다.
- 두 경로가 **같은 정규화**를 거친다 (`spoken_text_for_tts(raw, terms=_paper_speak_terms(cid))`). 이게 어긋나면 뒤에 읽을 때의 요구가 묻는 이름과 다른 이름으로 짓고, 지은 것이 하나도 재사용되지 않는다.
- 문장을 안 보내는 예전 폰은 논문을 당기는 경로로 그대로 간다.
- 상한: 600문장, 문장당 2000자.

### 부산물: 채점은 제대로 돌았다

`queued` 0건, 네 줄 모두 `sure_code=ok`, `sym_used=1`. 일부러 틀리게 읽은 문장은 `slot_said 15 3 6 6 8 0 0 1 2` — 여섯·일곱번째 칸은 소리가 아예 없어서 0점, 2/6 통과.

단 **각 덩어리의 첫 단어가 기준보다 소리를 더 읽은 것으로 세어서** 68→55, 77→71, 40→34 으로 깎여다. 68 은 통과선을 넘는데 55 로 떨어졌다. design/382 에서 미리 잰 18.9% 꾬리가 첫 단어에 모여 나타나는 것이다. 창을 중간점으로 좁힐 것인가는 619개 녹음에 다시 잰 뒤에 정한다.

## 왜 다시 분석하는 건 답이 아닌가

기준 소리는 논문에 매달려 있지 않다. 파일 이름이 `sha256(speak_norm_version|voice|BREAK_MS|PAD_MS|SKIP_COST|문장글자)[:24]` 다. 같은 논문을 다시 분석하면 같은 문장이 나오고 같은 이름이 되어서 **이미 있는 파일을 그대로 쓴다.** 새로 지어지는 게 없다. 짓는 규칙이 바뀌면 이름이 같이 바뀌니, 옛 규칙으로 지은 소리가 몰래 쓰일 일도 없다.

그래서 고칠 자리는 분석이 아니라 **여는 순간 서버에 말하는 것**이었다.
