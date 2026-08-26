# 141 — Mobile sentence notes (듣고 적기)

Modules (구현 시): Flutter reader · notes sync API (웹 [16](16-sentence-notes.md) · [17](17-rumination-revisions.md) GCS 노트)  
받침: [16](16-sentence-notes.md) · [33](33-mobile-flutter.md) · [140](140-mobile-mvp-backlog-split.md)

**상태: 설계 잠금 · 이 문서만으로는 코드 구현하지 않음.**  
구현은 별도 「진행해 / go」 턴에서 **이 칩만**.

## 무엇인가

웹에는 **듣고 적기** 노트가 있다. 앱 읽기에는 없다.  
현재 문장에만 묶인 노트를 앱에서도 쓰고, 가능하면 **같은 유저 GCS 노트**로 웹과 이어진다.

| 포함 (구현 시) | 미포함 |
|------|--------|
| 현재 `sentence_id` 노트 열기/저장/닫기 | 리비전·구간 되새김질 UI (후속 · 17) |
| TTS와 함께 쓰는 「듣고 적기」 톤 (웹 16 불변) | AI 채점·요약·힌트 |
| 문장/그림 커서 **불변** | APK 자체 업데이트 · compound |
| 킬 스위치 + status 플래그 | Live Enable / IPS |

## Product (locked for next implement turn)

1. **앱만** 1차 (웹 16은 이미 있음 · 계약만 맞춤)  
2. 노트는 **현재 문장 하나** (`sentence_id`) · AI 판정 없음  
3. 열기/저장/닫기가 `sentence_index` / `figure_index`를 **바꾸지 않음**  
4. 검증: **폰 + Live** (로그인 유저 · 노트 저장 후 재오픈)  
5. fail-closed: 저장 실패 시 **성공한 척 닫지 않음**

## Kill / rollback (구현 시)

- `ASR_MOBILE_SENTENCE_NOTES=0` (가칭) → status false → 앱 노트 UI 숨김  
- Revert PR · 이전 APK

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

_(구현 칩에서 부여)_

## Device / E2E pin

_(구현 후)_

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
