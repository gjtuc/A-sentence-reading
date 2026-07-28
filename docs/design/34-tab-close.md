# 34 — Paper tab close (×)

모듈: `static/app.js` · `static/styles.css` · 논문 탭 줄

## 무엇을

크롬처럼 열린 논문 탭 **오른쪽 ×** 로 탭만 닫는다.  
보관본·GCS·원본 파일은 지우지 않는다 (보관 「삭제」와 다름).

## 닫을 때 저장 (탭 범위만)

| 저장 | 이유 |
|------|------|
| 문장/그림 진행 (`AsrProgress`) | 탭별 읽기 위치 |
| 성찰 노트 draft/disk flush | 키보드 기록 |
| (이미 IDB에 있는) 음성 노트 | 탭/문장 키로 묶임 · 추가 업로드 없음 |

| 저장 안 함 | 이유 |
|------------|------|
| TTS 설정 | 전역 · 다른 탭에도 영향 |
| 테마/레이아웃 선호 | 전역 |

## UI

- 탭 라벨 오른쪽 `×` (`aria-label="탭 닫기"`)
- `pointerdown`/`click` 은 탭 드래그·활성화와 **분리** (`stopPropagation`)
- 실논문 탭 ≥1 이면 탭 줄 표시 (1개여도 ×로 mock 복귀 가능)

## 동작

1. 닫을 탭이 **활성**이면: TTS 중지 → 노트 flush → snapshot → progress save  
2. `papers` 에서 제거  
3. 남은 실논문 있으면 그중 하나 activate · 없으면 `loadMock()`  
4. `renderPaperTabs` · 헤더 배지 갱신

## 비목표

- 보관 목록/GCS 삭제 (기존 「보관 삭제」)
- 닫기 확인 다이얼로그 (크롬과 같이 즉시 닫기; 저장은 동기 flush)
- Live Enable / IPS (Trading Gate — ASR 범위 밖)

## 버전

0.2.42
