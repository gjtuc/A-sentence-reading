# 07 — Typography tokens

문장 패널만 Immersive Reader 레시피. 그림 패널은 중립 다크 UI.

## CSS 변수 (단일 출처: `styles.css` `:root`)

| 토큰 | 1차 값 | 이유 |
|------|--------|------|
| `--bg` | `#0f0f0f` | 고대비 배경 |
| `--fg` | `#e3e3e3` | 본문 |
| `--fg-muted` | `#9a9a9a` | 메타 |
| `--sentence-max-ch` | `27ch` | 짧은 줄 (~기존 34ch의 4/5) |
| `--sentence-size` | `1.45rem` | 한눈에 |
| `--sentence-line` | `2.2` | 줄간격 |
| `--letter-space` | `0.04em` | crowding 완화 |
| `--word-space` | `0.12em` | 단어 간격 |
| `--font` | Segoe UI, Sitka Text, Calibri, Malgun Gothic, sans-serif | Sitka 있으면 사용 |

## 바꾸지 말 것 (제품 감각)

- 문장 패널을 카드 그림자로 “예쁘게” 만들지 않음
- 보라/네온 액센트 금지
- 기본값을 라이트 테마로 뒤집지 않음 (설정 UI는 M5+)

## 사용자 조절 (M5+)

토글 후보만 적어둠. 1차 구현 안 함.

- spacing on/off
- max-ch: 28 / 34 / 42
- theme: dark / sepia (Irlen 유사는 연구 메모 수준)

조절 시 localStorage `asr.typo.v1`.

## 검증

모니터에서 영문 80–100단어 문장이 **한 화면 폭 안에서 3–6줄** 정도면 OK.  
한 줄에 80자 넘게 붙으면 `--sentence-max-ch`를 줄인다.
