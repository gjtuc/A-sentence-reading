# Design index — 구현용 쪼개진 설계

상위 제품·UX는 [PRODUCT.md](../PRODUCT.md) · [UX.md](../UX.md) · [ARCHITECTURE.md](../ARCHITECTURE.md).  
아래는 **코드를 쓰기 직전에 필요한 계약·알고리즘·상태·한계**다.

| # | 문서 | 채운 빈틈 |
|---|------|-----------|
| 00 | [00-milestones.md](00-milestones.md) | 무엇을 언제 구현할지 · 합격 기준 |
| 01 | [01-data-model.md](01-data-model.md) | 필드·ID·직렬화·불변조건 디테일 |
| 02 | [02-pdf-extract.md](02-pdf-extract.md) | PyMuPDF 전략·그림 필터·다단·실패 |
| 03 | [03-sentence-split.md](03-sentence-split.md) | 경계 규칙·약어·픽스처 |
| 04 | [04-api-contract.md](04-api-contract.md) | HTTP 스키마·에러 코드 |
| 05 | [05-session-store.md](05-session-store.md) | 세션 수명·디스크 레이아웃 |
| 06 | [06-ui-states.md](06-ui-states.md) | UI 상태머신·빈/로딩/에러 |
| 07 | [07-typography-tokens.md](07-typography-tokens.md) | CSS 토큰 수치·변경 규칙 |
| 08 | [08-errors.md](08-errors.md) | 에러 분류·사용자 메시지 |
| 09 | [09-testing.md](09-testing.md) | 단위/계약 테스트·픽스처 |
| 10 | [10-security-limits.md](10-security-limits.md) | 업로드·경로·리소스 한도 |
| 11 | [11-figure-collapse.md](11-figure-collapse.md) | 스플리터 드래그로 그림 접기·문장 상단화 |
| 12 | [12-gemini-debone.md](12-gemini-debone.md) | Gemini로 저자·인용 가시 제거 · Title/Abstract/Body |

**구현 순서 (강제):** 00 → 01 → 04/05 뼈대 → 02 → 03 → 06/07 UI 연결 → 08/09/10 보강.  
스플리터(11)는 UI 스켈레톤과 함께 구현 가능 (PDF와 무관).
