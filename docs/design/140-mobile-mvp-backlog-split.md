# 140 — Flutter MVP backlog split (from design/33)

Modules: docs only (`33` · `00-milestones` · `README` · this file)  
받침: [33](33-mobile-flutter.md) · [139](139-fig-ref-chip-formal.md) · [142](142-no-keyboard-sentence-notes.md)

## 무엇인가

설계 **33**의 「남은 실기기 완성도」는 **큰 가방**이다.  
한 턴에 통째로 비우지 않는다. **작은 칩으로 쪼개고**, 그중 **하나만** 다음 구현으로 잠근다.

| 포함 | 미포함 |
|------|--------|
| 33 후속 목록을 **번호 칩 후보**로 정렬 | 이번 칩에서 앱/서버 **기능 코딩** |
| 33 합격 기준 중 실기 로그인 체크 **닫기** (이미 다수 E2E) | APK 자체 업데이트 구현 |
| **다음 구현 칩 재정렬** (노트 취소 후) | DOCX 옆논문 · compound · **모바일 노트(141)** (사용자 삭제) |
| milestones / README 반영 | Live Enable / IPS |

## Product (locked)

1. **A** — 이번 턴은 **쪼개기 + 다음 칩 설계만** (코딩은 별도 「진행해」)  
2. 우선순위는 에이전트 제안: **읽기 본선 패리티**가 보관·설정 UI보다 앞  
3. **삭제 유지**: DOCX 옆 논문 · compound 1a/1b — 후보에 넣지 않음  
4. **APK 자체 업데이트**는 항상 **맨 마지막**  
5. 검증: Live status + 폰 APK가 Live 보관 목록을 연다 (MVP 경로 증거).
6. **~~모바일 문장 노트(141)~~ — 취소** · 웹 키보드 노트 제거는 **[142](142-no-keyboard-sentence-notes.md)**.

## 쪼갠 목록 (구현 순서)

| 순서 | 칩 | 한 줄 |
|------|-----|--------|
| ~~취소~~ | ~~[141](141-mobile-sentence-notes.md)~~ | ~~모바일 문장 노트~~ → **[142](142-no-keyboard-sentence-notes.md)** 로 웹도 끔 |
| (보류) | (미번호) | 모바일 **리비전·구간 되새김질** — 웹 [17](17-rumination-revisions.md); 키보드 노트 없음 → **후속 재검토** |
| **다음 →** | [146c](146c-mobile-kakao-oauth-scheme.md) | ~~카카오 OAuth scheme (flutter_web_auth_2)~~ |
| 2 | [146b](146b-account-warehouse-merge.md) | 계정 창고(논문) 병합 — **미구현** |
| 3 | (미번호) | **사용량** 앱(관리자) — [27](27-usage-metering.md) |
| 4 | (미번호) | **쓰다가 주시는 수정** — 실사용 발견 시 그때 칩 |
| **맨 뒤** | (미번호) | **APK 자체 업데이트** |

**이미 끝난 것 (33 가방에서 빼기):**  
로그인·게이트·보관·읽기·TTS·테마·업로드·취소·hang·격리·Fig 칩(139) · 키보드 노트 끔(142) · 재분석(145) · 계정 연결 UI(146a) · 카카오 scheme(146c) 등 — milestones 0.2.55–0.3.64.

## Kill / rollback

- Revert docs PR · 목록만 롤백 (런타임 변경 없음; 142 런타임은 별도)

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

문서만 · 런타임은 후속 칩(142=**0.3.58**)이 올리면 따라감

## Device / E2E pin

- Live `/api/status`: `version=0.3.57` (이 칩 당시) · `live_only=true` · `mobile_library=true` · `mobile_reader=true`
- APK SM-G986N `versionName=0.3.57` → Library **보관 7건** · paper rows visible (MVP path; no new feature UI this chip)
- pytest `tests/test_mobile_mvp_backlog_split.py`
- Kill: revert docs PR

Do not paste emails, cookies, tokens, or secrets into chat/PR.
