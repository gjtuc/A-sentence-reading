# 468 — 서버 합치기가 GCS 목록의 논문도 찾게

## 증상

0.3.481에서 "짝과 합치기"를 다시 누르자 기기에서는 겹친 SI가 빠지고 189문장이 됐지만
(`paper_merge_local_done` `prior_merge=1`, `stripped_sent_n=4`), 서버 합치기가
`server_sync=http_404`로 실패해 보관함에는 여전히 SI가 따로 남았다.

## 원인

보관함 목록(`/api/cache/papers`)은 인스턴스 로컬 index ∪ 사용자 GCS index다.
`merge_supplementary`는 로컬 index만 읽었다. 배포 직후 새 Cloud Run 인스턴스에는
그 인스턴스가 분석한 논문만 있으므로 `cache_not_found`(404)가 났다.
design/467 이전에는 앱이 기기 합치기만 하고 서버를 부르지 않아 드러나지 않았다.

## 고침

- `_index_entries_with_remote`: 로컬 index와 GCS index를 `merge_index_entries`로 합쳐
  짝과 합치기 가능 여부를 본다(목록과 같은 규칙: GCS에 있는 로컬 행만).
- `_pull_from_gcs`: 메인과 SI를 GCS에서 내려받아 인스턴스 사본을 덮어쓴 뒤 합친다
  (design/121: 공유 디스크의 남은 사본을 믿지 않음).
- 저장 뒤 기존대로 `upload_paper_cache`가 두 논문과 index를 GCS에 올린다.
- GCS가 꺼져 있으면 예전처럼 로컬만 본다.

## 시험

- `tests/test_design_468_merge_remote_index.py`
