# 93 — Remove Live Enable / IPS footer from app UI

Modules: `mobile/lib/screens/reader_screen.dart` · `shadowing_practice_screen.dart`  
받침: [63](63-mobile-reader.md) · [82](82-shadowing-practice-loop.md)

## 무엇인가

읽기(및 쉐도잉) 화면에 보이던 `Live Enable / IPS: Trading Gate (ASR out)` 문구 제거.  
개발용 주석·설계 문서의 Trading Gate 언급은 유지.

| 포함 | 미포함 |
|------|--------|
| 유저 대면 Text 위젯 제거 | 웹 헤더/가이드 문서 전면 정리 |
| pytest: reader에 문구 없음 | Live Enable 기능 자체 |

## Product (locked this chip)

User-facing Live Enable / IPS chrome must not appear in the app.

## Kill / rollback

- restore footer Text widgets

## Version

**0.3.7** · status + pubspec

## Live Enable / IPS

이번 칩의 대상(표시만 제거). 기능 킬 아님.
