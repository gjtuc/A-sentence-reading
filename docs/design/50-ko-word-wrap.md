# 50 — 한글 번역 어절 줄바꿈

모듈: `static/styles.css` (`.sentence-ko`) · 받침 [07](07-typography-tokens.md) · [39](39-translate-side-by-side.md)

## 무엇을

번역 on 시 한글 문장 박스에서 **음절 중간 줄바꿈**을 막고, **띄어쓰기(어절) 경계**에서만 줄이 넘어가게 한다.

| CSS | 역할 |
|-----|------|
| `word-break: keep-all` | CJK를 공백 전까지 한 덩어리로 |
| `overflow-wrap: break-word` | 공백 없는 초장문(화학식 등)은 상자 밖으로 안 나가게 예외 허용 |
| `line-break: strict` | 과도한 CJK 임의 브레이크 완화 |

영문 `.sentence-text` · 각주 칩 · 되새김질은 **이번 범위 밖** (후속 UX).

## 비목표

- Live Enable / IPS — Trading Gate (ASR 밖)
- 서버에서 강제 개행 삽입 · 형태소 분석기
- 노트/되새김질 타이포 (후속)

## 불변

- 문장↔그림 인덱스 독립
- EN\|KO 좌우 동형 레이아웃 (39) 유지
- 타이포 토큰(`--sentence-size` 등) 값은 바꾸지 않음 — **줄바꿈 규칙만**

## 버전

웹 **0.2.58** · status `ko_word_wrap: true`

## Version pin

Web/mobile **0.2.95** (invite redeem E2E · access session clear — see [67-access-gate.md](67-access-gate.md)).
