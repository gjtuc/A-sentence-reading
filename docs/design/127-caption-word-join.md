# 127 — Caption word-join (Elsevier line breaks)

Modules: `pdf/extract.py` · `llm/typography.py`  
받침: [125](125-caption-anchored-figures.md) · [126](126-soft-caption-labels.md) · [02](02-pdf-extract.md)

## 무엇인가

Elsevier 등 PDF는 `Fig.` / `3.` / `TEM` 처럼 **단어마다 줄바꿈**을 넣는다.  
줄 단위 매칭은 `"Fig."`만 보고 캡션을 버려 Fig/Scheme이 통째로 빠진다.  
단어를 같은 줄로 이어 붙여 `Fig. 3. …`를 복원한 뒤, 기존 soft/punct 규칙으로 추출한다.

| 포함 | 미포함 |
|------|--------|
| 단어→줄 재조립으로 라벨 캡션 복원 | Gemini/vision 캡션 추정 |
| 같은 y의 `Fig.` + `4. 제목` 블록 이어붙임 | 표/그림 클립 폭 확대 |
| pipeline `rich-v11` | 캡션 말줄임 UI · compound |

## Product

1. 캡션 라벨(Fig/Figure/Scheme/Table + 번호)이 텍스트에 있으면 **빠짐없이** 추출  
2. 본문 `Figure 4 illustrates…` 는 계속 거절  
3. 생성형 API 없이 **결정적** 텍스트 재조립만  

## Kill / rollback

Revert PR · `PIPELINE_VERSION` 되돌리기

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.41** · pipeline **rich-v11**
