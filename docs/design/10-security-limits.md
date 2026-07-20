# 10 — Security & limits

로컬 단일 사용자 전제. 그래도 path·크기 가드는 넣는다.

## 한도

| 항목 | 값 |
|------|-----|
| 업로드 최대 | 50 MiB |
| 페이지 소프트 | 80 (warning) |
| figures 최대 | 200 |
| sentences 최대 | 5000 |
| 동시 세션 | 8 (LRU) |
| extract timeout | 120 s |

## Path

- `session_id` / `figure_id`: `^[A-Za-z0-9_.-]+$` 만 허용
- `out_dir.resolve()` 가 `data/extracted.resolve()` 하위인지 검사
- `..` 포함 요청 → 400

## 파일 타입

- 확장자 `.pdf` (대소문자 무시)
- 매직 바이트 `%PDF` 확인 ( Milstone M2+ )

## 비목표

- 인증/멀티유저
- HTTPS 강제 (localhost)
- 악성 PDF 샌드박스(격리 프로세스) — 필요해지면 M5+에서 subprocess 검토

## 개인정보

논문 PDF는 사용자 디스크에만. 텔레메트리 없음.
