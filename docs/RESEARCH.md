# Research notes

이 제품이 **무엇을 빌리고**, **무엇과 다른지**를 짧게 고정한다.

## Immersive Reader (Microsoft)

Word/Edge의 몰입형 리더: 텍스트를 읽기용으로 **다시 배치**하고, 사용자가 테마·간격·열 너비를 조절한다.

우리가 빌리는 것 (룩·원리):

- Dark theme (고대비)
- Increased text spacing → visual crowding 완화
- Narrow column / short line length → 시선 폭 축소
- (선택) line focus 개념 — 우리는 단위를 **한 문장**으로 더 강하게 제한

우리가 안 쓰는 것:

- Azure Immersive Reader SDK / iframe
- 음절 분리·품사 색칠·그림 사전 (1차 범위 밖)
- 단어 단위 TTS 하이라이트를 핵심으로 삼지 않음

공식·SDK:

- [Use Immersive Reader in Word](https://support.microsoft.com/en-us/office/use-immersive-reader-in-word-a857949f-c91e-4c97-977c-a4efcaf9b3c1)
- [Immersive Reader SDK reference](https://learn.microsoft.com/en-us/azure/ai-services/immersive-reader/reference) — `themeOption`, `increaseSpacing`, `textSize`
- [Research behind Immersive Reader](https://learn.microsoft.com/en-us/training/educator-center/product-guides/immersive-reader/research)

인용되는 방향 (요약):

- 넓은 글자 간격 → 난독증·crowding 연구 (Zorzi 등)
- 짧은 줄 → 읽기 속도 향상 (Schneps 등, MS 페이지에 ~27% 언급)
- 페이지 색/오버레이 → 시각적 불편 완화 (Wilkins 등)

## RSVP / 속독 앱과의 차이

단어 하나씩 빠르게 보여주는 RSVP는 고속에서 **이해·추론이 떨어진다**는 쪽 연구가 많다.  
이 제품은 속독이 아니라 **문장 단위 느린 반복**이다.

## 유사 학술 PDF 도구 (차별점)

| 도구 | 하는 일 | 우리와 다른 점 |
|------|---------|----------------|
| [RailReader2](https://sjvrensburg.github.io/railreader2/) | 줄/블록 레일 읽기, 그림 팝아웃 | PDF 페이지 위 항해; **한 문장만** UI 아님 |
| ResearchPrism / Lumenfolio | 그림 탭 + AI | AI·증거 중심 |
| aipdfreader | 페이지 단위 AI 튜터 | 페이지/챗 중심 |
| Europe PMC | 피겨 캐러셀 | 초록 아래 브라우징; 문장 읽기 루프 없음 |

**틈:** 위 한 문장 + 아래 그림 캐러셀 + **독립 수동 동기화** 조합은 찾기 어렵다.

## 그림–텍스트 자동 링크 연구

최근 “Connecting the Dots” 등 cross-modal link 연구가 있다.  
우리는 1차에서 **자동 링크를 제품 필수로 두지 않는다** — 논문 Fig 배치와 설명 흐름 때문에 수동이 맞다고 본다. 나중에 “힌트만” 넣을 여지는 있다.

## 구현 시 참고 기술

- PDF 그림/텍스트: PyMuPDF
- 문장 경계: `pysbd` 후보 (정규식만으로 `Fig.` `et al.`이 잘림)
- UI: CSS variables로 Immersive 레시피 고정 ([UX.md](UX.md))
