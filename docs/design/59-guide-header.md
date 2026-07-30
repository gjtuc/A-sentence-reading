# 59 — Guide 헤더 배치 (밖 / `⋯` 안)

모듈: `static/index.html` · `styles.css` · `app.js`

## 무엇을

헤더에 **Guide** 버튼을 두고, 기본은 **파일 열기 · Guide · `⋯`**.  
체크박스「Guide를 `⋯` 안에 넣기」로 버튼을 overflow 메뉴로 옮길 수 있다.

| 기본 (`nestInMore: false`) | 체크 시 (`nestInMore: true`) |
|----------------------------|------------------------------|
| 파일 열기 · **Guide** · `⋯` | 파일 열기 · `⋯` (Guide는 메뉴 맨 위) |

| 포함 | 미포함 (후속) |
|------|----------------|
| Guide 버튼 · 안내 `<dialog>` | 화면 단축키 hint 줄 삭제·축소 |
| `asr.guide.v1` · UID별 키 | 안내 문구 대폭 확장 |
| DOM 이동 (`guideOutsideSlot` ↔ 메뉴) | Live Enable / IPS |

## UX

- Guide 클릭 → 단축키·읽기 불변조건 안내 다이얼로그
- 체크 변경 → 즉시 버튼 자리 이동 · localStorage 저장
- 다이얼로그 열 때 `⋯`·TTS·보관 다이얼로그는 닫음
- 메뉴 안일 때 `role="menuitem"` · 밖이면 role 제거

## Pref

```json
{ "nestInMore": false }
```

키: `asr.guide.v1` 또는 `asr.guide.v1.{uid}`  
EDGE: 손상 JSON · 비객체 → `nestInMore: false`

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 문장·그림 인덱스 변경
- 화면 `.hint` 줄 제거 (다음 검토)

## 버전

웹 **0.2.67** · status `guide_header: true`
