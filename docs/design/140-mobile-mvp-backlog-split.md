# 140 — Flutter MVP backlog split (from design/33)

Modules: docs only (`33` · `00-milestones` · `README` · this file · next-chip lock [141](141-mobile-sentence-notes.md))  
받침: [33](33-mobile-flutter.md) · [16](16-sentence-notes.md) · [139](139-fig-ref-chip-formal.md)

## 무엇인가

설계 **33**의 「남은 실기기 완성도」는 **큰 가방**이다.  
한 턴에 통째로 비우지 않는다. **작은 칩으로 쪼개고**, 그중 **하나만** 다음 구현으로 잠근다.

| 포함 | 미포함 |
|------|--------|
| 33 후속 목록을 **번호 칩 후보**로 정렬 | 이번 칩에서 앱/서버 **기능 코딩** |
| 33 합격 기준 중 실기 로그인 체크 **닫기** (이미 다수 E2E) | APK 자체 업데이트 구현 |
| **다음 구현 칩 = 141** 설계 잠금 | DOCX 옆논문 · compound (사용자 삭제) |
| milestones / README 반영 | Live Enable / IPS |

## Product (locked)

1. **A** — 이번 턴은 **쪼개기 + 다음 칩 설계만** (코딩은 별도 「진행해」)  
2. 우선순위는 에이전트 제안: **읽기 본선 패리티**가 보관·설정 UI보다 앞  
3. **삭제 유지**: DOCX 옆 논문 · compound 1a/1b — 후보에 넣지 않음  
4. **APK 자체 업데이트**는 항상 **맨 마지막**  
5. 검증: Live status + 폰 APK가 Live 보관 목록을 연다 (MVP 경로 증거). 노트 UI는 **141 구현 칩**에서.

## 쪼갠 목록 (구현 순서)

| 순서 | 칩 | 한 줄 |
|------|-----|--------|
| **다음 →** | **[141](141-mobile-sentence-notes.md)** | 모바일 **문장 노트**(듣고 적기) — 웹 [16](16-sentence-notes.md) 패리티 |
| 2 | (미번호 · 141 후) | 모바일 **리비전·구간 되새김질** — 웹 [17](17-rumination-revisions.md); **노트 선행** |
| 3 | (미번호) | 보관 **재분석** 앱 UI — 웹 [20](20-source-backup.md) |
| 4 | (미번호) | **계정 연결** 앱 UI — [23](23-multi-auth-link.md) |
| 5 | (미번호) | **사용량** 앱(관리자) — [27](27-usage-metering.md) |
| 6 | (미번호) | **쓰다가 주시는 수정** — 실사용 발견 시 그때 칩 |
| **맨 뒤** | (미번호) | **APK 자체 업데이트** |

**이미 끝난 것 (33 가방에서 빼기):**  
로그인·게이트·보관·읽기·TTS·테마·업로드·취소·hang·격리·Fig 칩(139) 등 — milestones 0.2.55–0.3.57.

## Kill / rollback

- Revert docs PR · 목록만 롤백 (런타임 변경 없음)

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

문서만 · 런타임 **0.3.57** 유지 (기능 코드 없음)

## Device / E2E pin

- Live `/api/status`: `version=0.3.57` · `live_only=true` · `mobile_library=true` · `mobile_reader=true`
- APK SM-G986N `versionName=0.3.57` → Library **보관 7건** · paper rows visible (MVP path; no new feature UI this chip)
- pytest `tests/test_mobile_mvp_backlog_split.py`
- Kill: revert docs PR

Do not paste emails, cookies, tokens, or secrets into chat/PR.
