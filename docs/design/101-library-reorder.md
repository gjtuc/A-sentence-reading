# 101 — Library long-press reorder

Modules: `library_screen.dart` · `library_controller.dart` · `library_order_models.dart`  
받침: [62](62-mobile-library.md)

## 무엇인가

보관 탭에서 문서 제목을 **길게 누른 뒤 드래그**해 위·아래 순서를 바꾼다.  
순서는 기기 prefs에 **uid 스코프**로 저장한다 (새로고침 후에도 유지).

| 포함 | 미포함 |
|------|--------|
| `SliverReorderableList` + delayed long-press | 서버/GCS 순서 동기 |
| prefs `asr.library.order.v1.{uid}` | 웹 보관 드래그 |
| 목록에 없는 id는 버리고, 새 문서는 목록 **앞** | Live Enable / IPS |

## Product

1. Long-press row → drag → drop.  
2. Tap still opens the paper.  
3. Logout does not leak another uid’s order into the next account (key scoped).

## Version

**0.3.15** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
