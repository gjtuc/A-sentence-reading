# 100 — Reader panel chrome toggle (tap)

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [97](97-reader-panel-expand.md) · [98](98-reader-split-drag.md) · [95](95-reader-swipe-nav.md)

## 무엇인가

문장·그림 **프레임 헤더**(이전/다음 · 인덱스 · TTS)를 **한 번 탭**으로 숨기고, 다시 탭하면 보이게 한다.

| 레이아웃 | 동작 |
|----------|------|
| 분할(원복) | 문장·그림 **어느 쪽**을 탭해도 **양쪽** 헤더가 같이 숨김/표시 |
| 문장/그림 전체 | 같은 공유 상태로 헤더 토글 |

더블탭 전체화면·스와이프·줌은 그대로.

## 비목표

- 앱 상단 논문 제목·「연습」줄 숨김
- 웹 · Live Enable / IPS

## Version

**0.3.14** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
