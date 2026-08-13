# 128 — Column-wide figure/table clips (less cropping)

Modules: `pdf/extract.py` · `llm/typography.py`  
받침: [125](125-caption-anchored-figures.md) · [127](127-caption-word-join.md) · [02](02-pdf-extract.md)

## 무엇인가

캡션 글자 상자가 좁으면 orphan 클립도 좁아져 **표 오른쪽 열·각주가 잘린다**.  
캡션이 속한 **단(column) 폭**으로 x 범위를 잡고, 옆 단 본문이 조금 들어와도 허용한다.

| 포함 | 미포함 |
|------|--------|
| orphan Fig/Table 클립을 단 폭(+소량 bleed)으로 | 캡션 문자열 말줄임 복원 |
| `find_tables` bbox 우선은 유지 | Gemini · compound |
| pipeline `rich-v12` | APK 자체 업데이트 |

## Product

1. Ewbank Table 1·2: 오른쪽 열·각주가 보이도록  
2. Fig 클립도 단 기준으로 과도한 좌우 잘림 완화  
3. 옆 단 글자 약간 혼입은 OK  

## Kill / rollback

Revert PR · `PIPELINE_VERSION` 되돌리기

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.42** · pipeline **rich-v12**
