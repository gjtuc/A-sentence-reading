# 79 — Shadowing practice opt-in (kill + settings)

Modules: `shadowing_practice.py` · Guide/Settings toggle · status `shadowing_practice`  
받침: 제품 잠금(쉐도잉 대화) · [68](68-mobile-shell-nav.md) Later「Keyboard notes → voice」

## 무엇인가

문장 **쉐도잉 연습** 시리즈의 **첫 칩**.  
서버 킬스위치 + 웹/앱 설정에서 **사용자가 켜고 끌 수 있는 옵션**(기본 **OFF**)만 넣는다.  
연습 루프·Gemini 청크·키보드 노트 제거·pitch·랜덤은 **Later**.

| 포함 (이 칩) | Later (후속 칩) |
|--------------|-----------------|
| `ASR_SHADOWING_PRACTICE` 킬 (기본 **off**) | Gemini ingest 청크 계획 |
| status `shadowing_practice` / `mobile_shadowing_practice` | TTS pitch 설정 칸 |
| 웹 Guide · 앱 설정 토글 (uid 스코프, 기본 OFF) | 연습 UI (듣기→같이 말하기→다음) |
| 로그아웃 시 다른 uid prefs 누수 방지 | 키보드 노트 삭제(데이터 포함) |
| | 랜덤 쉬움/보통 · 섹션 이어듣기 |

## Product (locked — series)

1. 키보드 텍스트 노트 제거(웹·앱, 데이터 삭제) → 말로 연습  
2. 청크: Gemini가 ingest 때 미리 · 같은 문장 다른 분할 OK · 앱이 자동 확장  
3. 흐름: TTS 1회 → TTS+자동녹음 동시 → 내 녹음 다시듣기 → 사용자「다음」  
4. 저장: 사용자 목소리만 · 섹션 이어듣기는 문장 전체 통과본만 · 스킵=빈 칸  
5. 고정+랜덤(쉬움/보통)은 **연습 화면**에서 선택  
6. TTS 설정에 pitch 칸 추가(후속) · 랜덤 난이도에 pitch 폭 반영  
7. **이 연습 전체** 설정 ON/OFF · **기본 OFF**  
8. 비용·지연보다 품질 우선(후속 칩)

## Kill / rollback

- unset / `ASR_SHADOWING_PRACTICE=0` → 서버 플래그 false · 클라이언트 토글 비활성  
- `=1` → 토글 활성(선호만 저장; 연습 UI는 후속)  
- Revert PR · APK 다운핀  

## Fail-closed / multi-user

- 기본 OFF · 서버 킬 OFF면 켜진 척 하지 않음  
- prefs 키에 **uid** 포함 · 로그아웃 후 이전 유저 ON 상태가 다음 유저에 보이지 않음  
- 이 칩은 녹음·GCS 경로를 만들지 않음 → 교차 유저 음성 격리 E2E는 **해당 없음(후속)**  

## Live Enable / IPS

이번 칩에서 **불필요** (ASR 밖 Trading Gate).

## Version

**0.2.96** · pubspec `0.2.96+1`

## Device / browser E2E (pre-merge)

- status `version=0.2.96`, `shadowing_practice=false` on live default  
- 로컬 `ASR_SHADOWING_PRACTICE=1` 시 토글 ON/OFF 저장 · uid 전환 시 격리  
- Live Enable / IPS: unchanged  

Do not paste emails, cookies, or tokens into chat/PR.
