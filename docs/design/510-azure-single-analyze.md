# design/510 — Azure 레이아웃 분석을 논문마다 한 번만 (0.3.519)

## 확인한 것

- 논문 한 편을 처리할 때 `prebuilt-layout` 분석을 논문 전체에 두 번 보냈다.
  - 읽기 순서: `vision_ocr.recover_pdf_text` → `body_headings.ordered_with_body_headings` → `layout_map.analyze_layout_map`
  - 그림·표: `extract.extract_figures` → `extract_figures_v2` → `layout_map.analyze_layout_map`
- 두 호출 모두 같은 업로드 파일(`tmp_path`), 같은 모델, 같은 옵션(`output=figures`)이다. Azure는 분석마다 쪽수로 요금을 매기므로 요금이 쪽수의 2배였다.
- design/151 문서 머리말은 "single analyze, reused downstream" 인데 실제로는 다시 쓰지 않았다.

## 결정

- `analyze_layout_map` 이 파일 내용의 sha256 으로 Azure 결과(client, result, operation id)를 30분, 최대 2개까지 들고 있는다.
- 같은 파일을 동시에 부르면 파일별 잠금으로 한 번만 보낸다. 다른 파일끼리는 서로 기다리지 않는다.
- `LayoutMap` 은 부를 때마다 결과에서 새로 만든다. 슬롯 계획이 `LayoutMap` 을 고치기 때문이다.
- 그림 조각(`get_analyze_result_figure`)은 operation id 로 나중에 받는다. Azure 가 24시간 보관하므로 30분 안에서는 문제없다.
- 실패한 분석은 담지 않는다. 다음 호출이 다시 보낸다.
- 다른 인스턴스로 넘어간 작업(lease reclaim)은 담아 둔 결과가 없어서 다시 보낸다. 이미 읽기 순서를 마친 작업은 원래 vision 이어받기로 순서 분석을 건너뛴다.

## 시험

- `tests/test_design_510_azure_single_analyze.py` — 같은 파일 두 번은 한 번만 보냄, 내용이 다르면 따로, 매번 새 `LayoutMap`, 실패는 담지 않음, 30분 지나면 다시 보냄.
