# 16 — Sentence reflection notes (듣고 적기)

모듈: `static/index.html` · `static/styles.css` · `static/app.js`  
저장: `localStorage` `asr.notes.v1` (서버 없음)

## 제품 결정

- **Enter** (노트 닫힌 상태) → 쓰기 오버레이 + **현재 문장 TTS 자동 재생**
- 문장 **텍스트 미리보기 없음** (읽고 적기 → **듣고 적기**)
- **다시 듣기** 버튼 없음 — **시트 아무 곳 클릭 = TTS** (입력칸·라벨 제외 → 커서만)
- 창을 **위로** 두어 뒤의 읽기 문장 패널을 가림 (시트를 길쭉하게 늘리지 않음)
- 뒤 화면은 거의 가려서 문장을 눈으로 훔쳐보기 어렵게
- 프롬프트(고정): *이 문장에서 알아차린 것을, 마치 여러 사람에게 들려준다고 생각하고, 주어 없이 적어보세요.*
- 노트 열린 채 · **입력칸에 커서가 없을 때** `←`/`→` = 저장 후 이전/다음 문장 · **Space** = TTS
- **Esc** = 입력칸 커서만 해제 (창 유지) → 바로 ←/→ · Space 가능
- **시트 밖 배경 클릭** = 저장 후 닫기
- 칸 안 **Enter 1–2회** = 줄바꿈 · **연속 Enter 3회** (포커스 위치 무관, 간격 ≤ ~900ms) = 닫기
- 닫기 제스처의 앞 두 Enter가 남긴 trailing `\n` 은 **저장 전에 제거** (기록용 아님)
- 읽기 화면 TTS는 **문장 클릭** (Enter는 노트용)
- AI 채점·요약·힌트 **없음** (이해의 주체 = 사람)

## 불변조건

- INVARIANT: 노트 열기/닫기·저장은 `figure_index` / `sentence_index`를 바꾸지 않는다.
- INVARIANT: 노트는 **현재 문장 하나**에만 묶인다 (`sentence_id`).
- INVARIANT: AI가 이해 여부를 판정하지 않는다.

## 저장 스키마

```json
{
  "<paperKey>": {
    "<sentenceId>": "user text…"
  }
}
```

- `paperKey`: `cacheId` → 없으면 `sessionId` → 없으면 `paper.id`
- 입력 debounce ~300ms · 닫을 때 즉시 flush
- 노트 열린 채 문장 `←/→` → 저장 후 새 `sentence_id` 로드 + TTS 재생

## UI

- Immersive 토큰 · TTS 설정 dialog 룩 재사용 금지
- 컴팩트 시트(프롬프트·힌트·입력칸)를 화면 **상단**에 배치 · 전용 TTS 버튼 없음
