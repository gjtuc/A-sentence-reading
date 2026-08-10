# 62 — Flutter 보관 목록 · open

모듈: `mobile/lib/api/paper_models.dart` · `client.dart` · `library_controller.dart` · `library_screen.dart`  
받침: [33-mobile-flutter.md](33-mobile-flutter.md) · [18-paper-library.md](18-paper-library.md) · [61](61-mobile-email-auth.md)

## 무엇을

Android Flutter MVP **보관 목록**:  
`GET /api/cache/papers` → 탭 → `POST …/open` → 세션 id를 읽기 탭에 표시.

| 포함 | 미포함 (후속) |
|------|----------------|
| 목록 · 빈 상태 · 로그인 유도 | 문장/그림 읽기 UI (→63) |
| open → `OpenedPaper` | TTS (→64) |
| pull-to-refresh | 여러 파일 · 이어올리기 |
| status `mobile_library` | |
| 단일 PDF 업로드 (→[70](70-mobile-upload.md)) | |

## EDGE

- 미로그인: 목록 API 호출 없이 안내
- `papers` 비배열 · id/title 누락 행 → 건너뜀
- open 404 / 빈 cache id → 에러 메시지
- 로그아웃 → `clearAll()`

## 비목표

- Live Enable / IPS — **Trading Gate. ASR 밖**
- 앱에 Gemini/GCS secret
- 문장↔그림 인덱스 변경 (읽기 후속)

## 버전

웹 **0.2.82** · pubspec `0.2.82+1`

## Version pin

Web/mobile **0.2.91** (upload → [70-mobile-upload.md](70-mobile-upload.md)).
