# 251 — Mate direct fetch (찾아보기 → 기기에서 합법 사본 가져오기)

Version: **0.3.242** · Status: **locked**  
Amends [237](237-pdf-import-doi-find-cta.md) · [241](241-saf-tree-write-copy.md) · [242](242-pdf-import-find-watch.md) · [247](247-pdf-import-downloads-bridge.md) · [248](248-pdf-import-downloads-inapp-browser.md)

## Intent

「SI/메인 찾아보기」에서 **가능하면 브라우저·Downloads 탭 없이** DOI에 대해 **열 수 있는 사본을 기기에서 받아** 기존 논문 폴더 복사 / ingest 큐로 넣는다.  
패턴·출판사 지원은 **하나씩 추가**하되, 기본 경로는 **합법 OA → 공식 API → 안전한 meta → 기존 브라우저 fallback** 이다.

## Locked product

1. **진입점:** `PdfImportScreen._openFind` (및 동일 CTA). advisory `doi` + `want_role` (`main`|`si`).
2. **오케스트레이션은 기기(로컬).** 바이트 GET은 Cloud Run이 출판사 PDF를 대신 받지 않는다 (공용 IP 차단·저작물 호스팅 금지).
3. **Tier 순서 (fail → next):**
   - **T0** 로컬: 이미 mate 있음 / 동일 DOI 쿨다운
   - **T1** 합법 OA: Unpaywall(및 동등 OA 해석기). `url_for_pdf` 우선. 페이월 우회 아님
   - **T2** 공식 출판사 API만 (키·계약·entitlement 있을 때). ScienceDirect **웹** 스크래핑 금지
   - **T3** 안전 패턴만: `citation_pdf_url` meta, 안정 DOI-prefix URL 템플릿, **옵트인·원격 kill**. HTML/CDN 페이월 우회·CAPTCHA 우회 금지
   - **T4** 기존: `https://doi.org/{doi}` 외부 브라우저 + find-watch + (필요 시) 파일 고르기
4. **검증 필수:** 호스트 allowlist·리다이렉트 제한·크기 캡·`%PDF`/`PK` 매직. HTML/challenge 본문은 실패.
5. **Sink:** 논문 폴더 writable → 트리에 기록 후 rescan/선택; 아니면 기존 `enqueuePickedPdfs` 경로. pairing/advisory/업로드 큐 **재사용**.
6. **SI:** 확장자·용량 화이트리스트. zip 전량 자동 금지(기본). Unpaywall은 SI를 거의 안 줌 → SI는 T3/T4 비중 큼.
7. **속도:** 기기 전역 직렬 + 호스트별 min interval. 탭 1회 = 오케스트레이션 1회. 백그라운드 대량 금지.
8. **서버 허용:** `mate/resolve`류로 **후보 URL·라이선스 메타 + 짧은 URL 캐시**만; 원격 패턴 레지스트리·kill. PDF 바이트 GCS 미러 금지.
9. **Evidence (add-only, DOI/URL/path 평문 금지):**  
   `mate_fetch_start` · `mate_fetch_candidate` · `mate_fetch_validate` · `mate_fetch_done` · `mate_fetch_fallback_browser`  
   (`ok`, `tier`/`source` enum, `elapsed_ms`, size/http **버킷**만).
10. **Downloads UX (제품 방향, 구현 시):** 상시 「다운로드」탭·중복 「다운로드에서 가져오기」는 **축소/제거 가능**. T4·복귀 시에만 「방금 파일 고르기」. 빈 화면은 **모드별 연결 CTA 하나**.

## Non-goals

- MANAGE_EXTERNAL_STORAGE / Downloads 몰래 스캔  
- Cloudflare·CAPTCHA 우회, Sci-Hub·그림자 도서관  
- 서버가 출판사 바이너리를 받아 사용자에게 배포  
- GetFTR/SeamlessAccess 필수화 (Later)  
- 이 문서만으로 Tier 구현 완료를 주장하지 않음 — **설계 고정**; 코드는 phase로 착수

## Implementation phases (causal order)

| Phase | Scope |
|-------|--------|
| **A** | Orchestrator + validate + sink; **T1 Unpaywall**; T4 fallback; evidence; global kill |
| **B** | T2 공식 API 1곳 (키·계약 있는 출판사만) |
| **C** | 원격 패턴 레지스트리 + `citation_pdf_url` / 안전 템플릿 |
| **D** | SI 실험 패턴 (옵트인) |
| **E** | (선택) GetFTR/기관 smart link |
| **UX** | Downloads 탭/중복 CTA 정리 (A와 병행 가능) |

Hook: `_openFind` → `LibraryController` mate fetch → 기존 copy/enqueue.  
모듈 예: `mobile/lib/mate_fetch/*` · 선택 `src/sentence_reading/llm/mate_resolve.py`.

## Tests

- Validate magic / HTML reject / size cap (Dart + optional Python)  
- Tier order unit (mock sources)  
- Route contract if `/api/mate/resolve` added  
- Regression: T4 still opens doi.org when kill/unsupported

## Version

**0.3.242** (design lock ship; Phase A+ code follows in later bumps)
