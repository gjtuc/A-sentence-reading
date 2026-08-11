# 115 — Reader panels must not clip without decoration

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [63](63-mobile-reader.md) · [98](98-reader-split-drag.md) · [114](114-library-open-empty-session.md)

## 무엇인가

보관에서 열면 **제목만** 보이고 본문이 회색 빈 칸인 경우(0.3.28에서도 재현):
열기 API는 문장을 내려주지만, 읽기 패널 `AnimatedContainer`가
`clipBehavior: Clip.hardEdge`만 주고 `decoration`이 없어 Flutter
`Container.build`에서 `decoration!` null check로 **레이아웃이 깨진다**.

| 포함 | 미포함 |
|------|--------|
| 문장/그림 패널 clip을 `ClipRect`로 분리 | GCS-first open |
| 위젯 테스트로 동일 함정 재발 방지 | shadowing chunks HTTP 500 |
| APK 0.3.29 · 실기 열기 본문 확인 | 설정 화면 카피 |

## Product

1. 열기 성공 후 읽기 탭에 **문장(및 가능하면 그림) UI가 그려져야** 한다  
2. 레이아웃 예외로 빈 본문을 「성공한 척」하지 말 것  
3. AuthZ·서버 계약 변경 없음 (클라 렌더만)

## Kill / rollback

- Revert PR / 이전 APK로 롤백  
- 서버 플래그 불필요 (모바일만)

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.29** (mobile `pubspec`; 서버 status version 동기화)

## Device / pytest

- flutter test: clip+no-decoration 회귀 · reader smoke  
- 실기: 보관 → 열기 → 본문 노드/문장 라벨 보임 · logcat에 Container null check 없음
