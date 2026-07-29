# 39 — 번역 표시: 영어 | 한글 좌우 동형

모듈: `static` sentence-stack · styles · translate UI  
받침: [35](35-translate-simple.md) · [36](36-translate-pipeline.md)

## 무엇을

「번역」이 켜져 있으면 현재 문장을 **영어 박스 | 한글 박스** 로 나란히 보여 준다.

| 요구 | 내용 |
|------|------|
| 배치 | 영어 **왼쪽**, 한글 **오른쪽**, 사이 여백 |
| 범위 | **전체화면·문장 확대·기본(축소) 분할** 모두 동일 규칙 |
| 동형 | 한글의 글자 색·크기·줄간격·자간·가운데 정렬을 영어 `.sentence-text` 와 동일 |
| TTS | 영어 프레임만 클릭 TTS (한글 프레임은 비클릭/비TTS) |

번역 off 또는 로딩 전: 영어만 단독 (기존과 같이 가운데).

## 비목표

- 줄 단위 강제 줄바꿈 동기화(서버가 줄을 나눠 주지 않음) — **시각 박스·타이포 동형**이 목표
- Live Enable / IPS (Trading Gate — ASR 밖)
- Flutter
- STT 패널 위치 변경

## DOM

```html
.sentence-stack
  .sentence-bilingual[.is-split]
    .sentence-frame #sentenceFrame → .sentence-text
    .sentence-ko-frame #sentenceKoFrame → .sentence-ko
```

`.is-split` 은 번역 표시 중일 때만.

## CSS

- `.sentence-bilingual.is-split`: `flex-direction: row`, `gap`, 양 칼럼 `flex: 1`
- `.sentence-ko` ← `.sentence-text` 와 동일 토큰 (`--sentence-size`, `--fg`, center…)
- `.sentence-ko-frame` ← `.sentence-frame` 과 동일 박스(테두리·패딩); `cursor: default`
- 문장 확대(`is-sentence-focus`)·브라우저 FS에서도 같은 row 규칙

## 불변

- INVARIANT: 번역 on/off는 읽기 인덱스를 바꾸지 않음
- INVARIANT: TTS 대상은 영문 프레임만

## 버전

0.2.47
