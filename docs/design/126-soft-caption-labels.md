# 126 — Soft caption labels (Fig/Table/Scheme without required punct)

Modules: `pdf/extract.py` · `llm/typography.py`  
받침: [125](125-caption-anchored-figures.md) · [02](02-pdf-extract.md) · [92](92-figure-caption-order.md)

## 무엇인가

출판사 PDF 중 캡션이 `Fig. 1 Title`처럼 **번호 뒤 구두점 없이** 시작하는 경우가 많다.  
125는 `Fig. 1.` / `Figure 2:` 만 인정해 이런 캡션을 놓쳤다.  
번호 뒤 **제목형 이어짐**도 캡션으로 인정하되, 본문  
`Figure 4 illustrates…` 는 계속 거절한다.

| 포함 | 미포함 |
|------|--------|
| `Fig./Figure/Scheme/Table` + 번호 뒤 구두점 **또는** 대문자 제목 | compound 1a/1b 쪼개기 |
| 본문 동사 이어짐 거절 | 캡션 말줄임 UI |
| pipeline `rich-v10` | APK 자체 업데이트 |

## Product

1. 캡션 라벨이 있으면 추출 (구두점 유무)  
2. 본문 문장형 시작은 캡션 아님  
3. 1a/1b 분해 안 함  

## Kill / rollback

Revert PR · `PIPELINE_VERSION` 되돌리기

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.40** · pipeline **rich-v10**
