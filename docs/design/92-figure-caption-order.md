# 92 — Figure caption-number order (+ graphical abstract)

Modules: `pdf/extract.py` · `llm/typography.py`  
받침: [02](02-pdf-extract.md) · [28](28-fig-ref-jump.md) · [44](44-compound-off.md)

## 무엇인가

Li–S 등에서 캐러셀 그림·표가 **뒤섞이거나** 일부만 보이는 구멍.  
캡션 번호 순으로 정렬하고, 초록 옆 **대표 이미지(GA)** 만 캡션 없이 예외 보관한다.

| 포함 | 미포함 |
|------|--------|
| Fig→Scheme→Table 번호 정렬 · (page,y,x) 타이브레이크 | 벡터-only 그림 · vision layout |
| `get_image_rects` 전 위치 | compound 1a/1b 재활성 |
| 초록 옆 큰 무캡션 → `Graphical abstract (p.N)` | 일반 무캡션 로고 전부 허용 |
| `rich-v8` (이 칩) · 이후 `rich-v9`([125](125-caption-anchored-figures.md)) · `rich-v10`([126](126-soft-caption-labels.md)) · pytest | Live Enable / IPS |


## Product (locked this chip)

1. Order: caption numbers (Fig, Scheme, Table).  
2. Uncaptioned: drop, **except** early-page abstract-adjacent large embed.  
3. Multi-rect embeds kept when captioned.

## Kill / rollback

- revert `extract.py` · `PIPELINE_VERSION` rich-v7 · prior APK

## Version

**0.3.6** · status + pubspec · pipeline **rich-v8**  
후속: **rich-v9** (0.3.39 · caption-anchored · [125](125-caption-anchored-figures.md)) · **rich-v10** (0.3.40 · soft captions · [126](126-soft-caption-labels.md))


## Live Enable / IPS

이번 칩에서 불필요함.  
기존 논문은 **재분석** 또는 stale pipeline 경로로 새 figures 반영.
