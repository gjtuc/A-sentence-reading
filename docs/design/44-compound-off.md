# 44 — Compound 자동 분리 파이프라인 끊기

모듈: `pdf/extract.py` (호출 제거) · status `compound_figures=false`  
받침: [29](29-compound-figures.md) (모듈 보관, ingest 비활성)

## 무엇을

파일 열기(PDF extract) 때 `(a)(b)` 패널 **자동 균등 분할을 하지 않는다.**  
통짜 그림만 캐러셀에 넣고, 확대는 **드래그 크롭**만 사용한다.

## 왜

- 자동 분리는 UI 안내가 없고 발동 조건이 좁아 체감·신뢰가 낮음
- 사용자가 쓰는 실조작은 드래그 크롭뿐이었음

## 어떻게

- `extract.py` 에서 `expand_compound_png` 호출 제거
- `compound.py` 모듈·단위 테스트는 **보관** (재활성화 가능)
- status: `compound_figures: false`
- `PIPELINE_VERSION` → **rich-v7** (옛 보관본의 이미 쪼갠 패널 목록은 stale → 재분석 시 통짜)

## 비목표

- 드래그 크롭 제거/변경
- Fig. 1a 본문 칩 점프 로직 삭제 (통짜여도 캡션 매칭은 기존)
- Flutter · Live Enable / IPS

## 버전

0.2.52
