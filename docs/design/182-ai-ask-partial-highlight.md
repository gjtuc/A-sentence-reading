# 182 — AI ask (clipboard + Google AI) · partial highlight in-sentence

**Parent:** [166](166-reader-annotations.md)  
**Status:** CLIENT IMPLEMENTED (APK/deploy pending)  
**Trigger:** 2026-09-07 — 길게 누르기 시트에 프롬프트 템플릿 + Google AI 연동; 색은 문장 **안** 드래그 구간만 칠하기.

---

## 0. Success definition (user-visible)

| Pass | Fail |
|------|------|
| 길게 누르기 시트에서 색 탭 → 같은 문장 안에서 드래그한 글자만 해당 색 하이라이트 | 색 탭만으로 문장 전체가 무조건 칠해짐 (구 P0 전체 하이라이트 기본 동작) |
| 드래그가 **다른 문장으로 넘어가지 않음** | 여러 문장에 걸친 선택 |
| 프롬프트 탭 → 클립보드 = `문장` + 빈 줄 2줄 + `프롬프트` 후 `https://www.google.com/ai` 외부 열기 | 앱 서버 Gemini 호출 / WebView DOM 주입 / 자동 전송 |
| 첫 설치(또는 목록 비어 있음 + 시드 플래그 없음)에 예시 프롬프트 1개 | 예시 삭제 후 재시드 |
| 예시 문구 편집·삭제 가능 | 예시 고정·잠금 |

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | 하이라이트 범위는 **현재 문장 카드 안만**. 교차 문장 선택 없음 (v1). |
| J2 | 제스처: **색 선택 → 드래그** (툴 모드). 드래그 없이 탭만으로는 칠하지 않음. |
| J3 | `char_range` = `[start, end)` plain-text offset in that sentence; **null 은 레거시 문장 전체**만 (기존 저장분 렌더). 신규 UI는 항상 non-null range. |
| J4 | 시트 역할 분리: **위 = 색(칠하기)**, **아래 = AI로 묻기(프롬프트 목록)**. 메모 필드는 유지(166). |
| J5 | AI 묻기 = **클라이언트만**. 클립보드 + `url_launcher` `LaunchMode.externalApplication`. 서버 LLM·evidence floor 불필요. |
| J6 | 타깃 URL **고정**: `https://www.google.com/ai` (사용자 선택; gemini.google.com 아님). |
| J7 | 자동 입력·자동 전송·JS 주입 **금지**. 스낵바: `복사됨 · Google AI에서 붙여넣기 하세요`. |
| J8 | 초기 시드 프롬프트 1개: `이 문장에 포함된 단어와 문법을 설명해줘.` — 편집·삭제 가능. `ai_prompt_seeded_v1` 플래그로 **한 번만** 시드. |
| J9 | 클립보드 포맷 (고정): |

```
{sentence plain text}


{selected prompt body}
```

(`\n\n\n` — 문장과 프롬프트 사이 빈 줄 2줄.)

| J10 | AI에 넣는 문장은 **문장 전체** plain text (하이라이트 구간이 있어도 ask는 문장 단위). |
| J11 | 166 스키마·GCS sync·reanchor 유지. 본 문서는 UI·범위·AI 동선만 lock. |

---

## 2. Long-press sheet layout

```
┌ 문장 주석 ─────────────────────────┐
│  [노랑][초록][파랑][분홍]            │  ← 탭 = paint mode (J2)
│  메모 (선택)                         │  ← 166 유지
│  [저장] / [삭제]                     │  ← 기존 주석 편집 시
├ AI로 묻기 ──────────────────────────┤
│  • 이 문장에 포함된 단어와 문법을…   │  ← 탭 = J5–J9
│  • (사용자 추가분)                   │
│  [프롬프트 관리]                     │  ← CRUD
└─────────────────────────────────────┘
```

- 색 탭 → 시트 dismiss → 해당 문장에서 드래그 대기 (짧은 힌트 스낵바 가능: `칠할 부분을 드래그하세요`).
- 프롬프트 탭 → 복사 + URL 열기 → 시트 dismiss.
- 「프롬프트 관리」: 추가 / 수정 / 삭제 (제목 필드 없이 body만 — body 한 줄 미리보기).

---

## 3. Partial highlight (in-sentence)

### 3.1 Interaction

1. Long-press sentence → sheet.
2. Tap color `C`.
3. Sheet closes; paint mode armed with `C` on that `sentence_key` only.
4. User drags over plain (or rich-rendered) text **inside that sentence**.
5. On drag end: create `AnnotationEvent`  
   `kind=highlight`, `color=C`, `sentence_id` / map key as 166,  
   `char_range=[start,end)`, `selector` = TextQuoteSelector of selected substring (권장, reanchor).
6. Cancel: back / tap outside / 다른 문장 탭 → paint mode off, no event.

### 3.2 Render

- `annotated_sentence_text`: 동일 문장에 **여러** `char_range` 하이라이트 허용 (겹치면 나중 `at` 또는 paint 순서 — 166 merge 규칙).
- Legacy `char_range == null` → 문장 전체 (기존 데이터).

### 3.3 Out of scope (v1)

- 밑줄 툴 모드 (166 P1 자리 유지)
- 여러 문장 span
- 단어 더블탭 자동 선택 (나중 편의)

---

## 4. AI ask prompts (local)

### 4.1 Store

- 기기 로컬 (`SharedPreferences` / 작은 JSON). 키 예: `asr.ai_ask_prompts.v1`
- 항목: `{ id, body, created_at }`
- 시드 플래그: `asr.ai_ask_prompts.seeded_v1 = true`

### 4.2 Seed (once)

If store empty **and** seeded flag false:

1. Insert one prompt: `이 문장에 포함된 단어와 문법을 설명해줘.`
2. Set seeded flag true.

User deletes all prompts → empty list OK; **do not** re-seed.

### 4.3 `runAiAsk(sentenceText, promptBody)`

1. `Clipboard.setData` with J9 format (`sentenceText` = current sentence plain).
2. `launchUrl(Uri.parse('https://www.google.com/ai'), mode: externalApplication)`.
3. SnackBar J7. On launch failure: still copied — tell user to open browser manually.

---

## 5. Mapping to 166

| 166 항목 | 182 |
|----------|-----|
| 범위 P0 문장 전체 / P1 char_range | **부분 하이라이트 = 기본 UX** (J1–J3). null = 레거시만 |
| bottom sheet 색+메모 | 시트에 **AI로 묻기** 섹션 추가 (J4) |
| GCS annotations | 하이라이트만 sync. 프롬프트는 **로컬 only** |
| server LLM | 사용 안 함 |

166 Product 표의 「범위」행은 본 문서로 lock 이관.

---

## 6. Implementation sketch (non-normative)

| Area | Touch |
|------|--------|
| `annotation_toolbar_sheet.dart` | 색 = arm paint; AI section + manage |
| `annotation_controller` / reader | paint mode state; drag → `char_range` |
| `annotated_sentence_text.dart` | selection/drag within sentence; multi-range paint |
| new `ai_ask_prompt_store.dart` | seed + CRUD |
| `url_launcher` + `Clipboard` | `runAiAsk` |
| tests | clipboard format; seed once; range clamped to sentence length |

Server / deploy / evidence floor: **no change** for this feature alone.

---

## 7. Acceptance checklist

- [x] Color → drag → only in-sentence substring highlighted (client)
- [x] Cannot extend selection past sentence bounds (paint keyed to sentence)
- [x] Legacy full-sentence (`char_range` null) still renders
- [x] Prompt tap copies J9 format and opens `https://www.google.com/ai`
- [x] Seed prompt exact string; editable/deletable; no re-seed after delete
- [x] No Gemini API / no WebView inject
- [x] Memo + existing annotation delete still work on sheet

---

## 8. Implementation hazards (필독)

구현 시 가장 많이 깨지는 지점. **상위 세 가지:** (1) plain/rich/cite **좌표계 불일치**, (2) 리더 **스와이프·스크롤 vs 드래그 충돌**, (3) reanchor가 **`char_range`를 안 고쳐** 조용히 엇나감.

### 8.1 Offset 진실 소스 (가장 중요)

하이라이트는 HTML이 아니라 **plain 문자 오프셋**이다.

| 규칙 | 내용 |
|------|------|
| 저장 | `char_range = [start, end)` on plain of the **same** string used for paint |
| 렌더 | `buildAnnotatedSpans` → plain 기준 슬라이스 (현 `rich_sentence.dart`) |
| clamp | 저장·렌더 모두 `0 ≤ start < end ≤ plain.length` — reanalyze 후 overflow **crash 금지** |
| 빈 선택 | `start == end` → **저장하지 않음** (J2) |
| 역드래그 | `min/max`로 정규화 후 half-open range |
| Unicode | Dart 인덱스는 UTF-16 code unit (grapheme 아님) — 테스트·주석에 고정 |

**표시 문자열 ≠ 저장 문자열 (필수 정렬)**

리더는 `cite.stripCiteMarkersForDisplay(cur.text)` 후 `AnnotatedSentenceText`에 넣는다. 드래그 offset도 **동일 파이프라인**이어야 한다:

1. `stripCiteMarkersForDisplay`
2. `plainFromRichHtml` (동일 함수·동일 공백 정규화)

한쪽만 strip하면 구간이 글자 수만큼 밀린다. AI 클립보드용 문장도 같은 plain을 쓸 것 (인용 마커가 프롬프트에 섞이지 않게).

**`<sub>` / `<sup>` / WidgetSpan**

`rich_sentence`는 첨자를 `WidgetSpan`으로 넣는다. `SelectableText` / `TextPainter.getPositionForOffset`은 Placeholder에서 오프셋이 어긋나거나 선택이 끊길 수 있다.

- “보이는 글자 수” ≠ `plain.length` 가능
- 선택은 **plain 좌표계로만**; paint 모드에서는 커스텀 드래그 + `TextPainter` hit-test가 전역 `SelectableText`보다 안전할 수 있음

**`plainFromRichHtml` 공백**

태그 제거 시 `\s+` → 한 칸. 원문 연속 공백·줄바꿈이 있으면 표시와 저장 plain이 달라질 수 있음 → 선택 경계는 항상 그 plain에 clamp.

### 8.2 `buildAnnotatedSpans` — 겹침·rich 손실

현 구현은 range를 start만 정렬한 뒤 한 번씩 자른다. **겹치는 두 하이라이트**가 있으면 뒤 range가 앞을 건너뛰거나 잘린다.

182는 한 문장에 여러 `char_range`를 허용하므로 구현 전:

- interval sweep으로 `[0, L)` 분할
- 각 조각에 덮인 색 (나중 `at` / 마지막 paint wins — 166 merge와 문서화)
- 테스트: `0–10` yellow + `5–15` green, `<sub>` 걸친 부분 구간

또한 현 코드는 하이라이트 구간을 **plain substring**에 다시 `buildRichSpans`한다. 원문 HTML의 `<sub>`가 구간에 걸치면 그 조각에서 **첨자 스타일이 사라질** 수 있다. 166 원래 알고리즘(rich segment의 `(plainStart, plainEnd)`에 annotation 입히기)에 가깝게 고치는 것이 사실상 필수에 가깝다. P0 문장 전체에서는 덜 티 났지만 부분 칠에서는 눈에 띈다.

### 8.3 제스처 전쟁 (리더)

문장 카드는 이미 제스처가 많다: 좌우 스와이프(문장 이동), 탭(크롬), 더블탭(확장), 스와이프 업(그림), long-press(시트), 세로 스크롤(긴 문장).

| 규칙 | |
|------|--|
| Paint ON | 문장 텍스트가 포인터를 먹고 `_SwipePager` **horizontal drag 비활성** |
| Paint OFF | 기존과 동일 |
| 세로 스크롤 vs 선택 | 슬롭(예: 8–16px)로 가로=선택 / 세로=스크롤 — 문서화 |
| 문장 이동 | `advanceSentence` 등 진입에서 **즉시 `clearPaintMode()`** (J1) |
| Figure ink | `figureInkMode`와 동시 ON 금지 — 한쪽 ON 시 다른쪽 OFF |
| 시트 | dismiss 후 `mounted` 체크; 색 탭 후 힌트 스낵바 권장 (`칠할 부분을 드래그하세요`) |

색만 누르고 드래그 없으면 **저장하지 않음**. 구 UI(색+저장=문장 전체)와 다르므로 힌트 없으면 “고장”으로 느껴진다.

### 8.4 시트 의미가 바뀜 (제품 버그)

| 구 (166 P0 UI) | 182 |
|----------------|-----|
| 색 + 저장 → 문장 전체 upsert | 색 → paint arm (이벤트 없음) |
| | 드래그 완료 → 새 id + non-null `char_range` |
| | 메모 저장 / 삭제 / AI = **별 동선** |

조심:

- 기존 주석 편집 시 “저장”이 색만 바꾸고 `char_range`를 **null로 덮으면** 부분 → 문장 전체 **퇴화**. 편집 = 기존 `charRange`/`id` 유지, 색·메모만 갱신.
- `removeAnnotationsForKey`는 그 키 **모든** 이벤트 tombstone. 부분 3개인데 삭제 한 번이면 전부 삭제. UX: 구간별 삭제 **또는** “이 문장 주석 전부 삭제” 문구 명시.
- `upsertHighlight`는 현재 `charRange`를 `annotationEventNow`에 **안 넘김** — 시그니처·JSON round-trip **반드시** 확장.
- 새 드래그 = **항상 새 id**. `existingId` upsert는 기존 하나 갱신 전용.

**로그인 (구현 시 lock)**

하이라이트는 `canAnnotate`(로그인) 필요. 프롬프트는 로컬 only.  
롱프레스에서 미로그인 시 시트 전체를 막으면 AI도 막힌다. 권장 lock:

- 미로그인: **AI 묻기 허용** / 색·메모·sync 비활성(또는 스낵바)
- 로그인: 전부

### 8.5 Reanchor / reanalyze

`annotation_reanchor.py`는 sentence_id → bookmark key → TextQuoteSelector 문장 매칭까지 하고 **`char_range`는 재계산하지 않는다.**

- 문장 앞 삽입 시 offset 전부 밀림 → **엉뚱한 구간 칠함** (orphan보다 나쁨).
- 현 클라이언트 selector `exact`는 **문장 전체** plain이다. 182에서는 **선택 substring**을 `exact`, 앞뒤를 `prefix`/`suffix`로 (plain only — `cur.text` raw substring에 태그 넣지 말 것).
- reanchor 성공 후 이상적으로 `new_plain.find(exact)` → `char_range` 갱신. 서버를 안 건드려도 **클라이언트 `reanchorToSession`만이라도** offset 재매칭 권장.

### 8.6 레거시 데이터

- sync된 `char_range: null` = 문장 전체 렌더 유지
- 신규 UI는 항상 non-null; 색 탭만으로 전체 칠 **복구하지 않음** (Fail 조건)
- legacy 전체 + 새 부분이 한 문장에 공존할 수 있음 → `at`/겹침 규칙 명시

### 8.7 AI 묻기

**금지:** Cloud Run/Gemini API, evidence 이벤트 “그냥” 추가, WebView+JS 자동 붙여넣기/전송, `gemini.google.com`으로 변경 (J6).

| 항목 | 함정 |
|------|------|
| 클립보드 | `sentence + "\n\n\n" + prompt` — 테스트로 문자열 고정; 문장은 **전체** plain (J10); 빈 prompt 실행 막기 |
| `url_launcher` | `LaunchMode.externalApplication`; `canLaunchUrl`만 믿지 말 것; 열기 실패해도 복사 성공 가능 → 메시지 분리 |
| 랜딩 | `google.com/ai`가 마케팅 페이지만 열릴 수 있음 — 제품적으로 “붙여넣기”가 전부 |
| 시드 | `empty && !seeded` → 예시 1개 + seeded; 전부 삭제 후 **재시드 금지**; prefs 키 변경 시 예시 재생성 주의 |
| 저장소 | 프롬프트를 annotations GCS에 **넣지 말 것** |
| 관리 UI | 시트 위 시트 → Navigator/`context` 주의 |

### 8.8 Paint mode 수명주기

최소 상태: `armedColor`, `armedSentenceKey`, `armedSentenceIndex`.

Clear: 드래그 완료, 취소, 문장 이동, 리더 pop, figure ink ON, (선택) app pause.

드래그 시작 시 key를 다시 resolve — arm key와 다르면 abort (잘못된 map에 저장 방지).  
연속 칠 모드를 암묵적으로 넣지 말 것 — 스펙은 한 번 칠고 clear에 가깝다.

### 8.9 번역 줄 / TTS / Chip

- 드래그·하이라이트는 **원문(영문) 줄만** — `textKo`에 paint 금지
- TTS 재생 하이라이트와 주석 배경이 겹쳐도 주석 span이 사라지지 않게
- `원문 미확인` Chip은 paint hit-test에서 제외

### 8.10 배포·가드·범위

이 기능만이면 서버 배포·evidence floor **불필요** (순수 클라 + 로컬 프롬프트).  
APK를 올리면 기존 `session_freshness` / `pre_deploy_guard` / 버전 bump 규칙은 그대로.

하지 말 것: Gemini proxy 추가, annotations sync **breaking** 스키마 변경, 166 tombstone/merge 의미 변경.  
`char_range`는 이미 스키마에 있음 — **쓰기·렌더·제스처·(권장) reanchor offset**만 연결.

### 8.11 테스트로 잠글 것

| 테스트 | 이유 |
|--------|------|
| plain offset + `<sub>` 걸친 부분 하이라이트 | rich/plain 불일치 |
| 겹치는 두 range | merge 버그 |
| `char_range` JSON round-trip | upsert 누락 재발 |
| clamp `end > length` | reanalyze 후 |
| 클립보드 `\n\n\n` | 포맷 regress |
| seed once / delete all / no reseed | J8 |
| paint 중 `advanceSentence` → arm clear | 교차 문장 |
| legacy null = full sentence | 기존 데이터 |

수동: 긴 문장 스크롤, 첨자 많은 문장, 로그인/비로그인, 스와이프 vs 드래그.

### 8.12 권장 구현 순서

1. `upsertHighlight`에 `charRange` + selector=선택 구간 (데이터 경로)
2. `buildAnnotatedSpans` segment-aware + overlap + 테스트
3. Paint mode + in-sentence drag (제스처 격리)
4. 시트: 색=arm; 저장/삭제=기존 주석용 재정의; 미로그인 AI 정책
5. AI prompt store + clipboard + `url_launcher`
6. Reanchor 시 `char_range` 재계산 (클라이언트만이라도)
7. APK / 실기기 스와이프·스크롤·첨자 문장 확인
