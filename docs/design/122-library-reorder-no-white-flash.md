# 122 — Library reorder: no white flash while dragging

Modules: `library_screen.dart` · (optional) small helper for proxy  
받침: [101](101-library-reorder.md)

## 무엇인가

보관 목록에서 길게 눌러 순서를 바꿀 때, 드래그 중인 행 주변이 **하얗게 번쩍**인다.  
Material 3 기본 `proxyDecorator` elevation + surface tint가 원인인 경우가 많다.

| 포함 | 미포함 |
|------|--------|
| 앱 `SliverReorderableList.proxyDecorator` 안정화 | 웹 보관 드래그 |
| 들어 올린 행·그림자 유지 | 순서 prefs/저장 로직 변경 |
| 흰 플래시 제거 | APK 자체 업데이트 · GCS open |

## Product (locked)

1. **앱만**  
2. 드래그 중 **완전 흰 플래시 없음**  
3. 들어 올린 행이 따라오는 느낌 유지 (색·그림자만 안정)  
4. **저장/reorder 로직은 이번 칩에서 안 건드림**  
5. APK 업데이트는 계속 뒤로  

## Kill / rollback

- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.36**

## Device / pytest

- unit: proxyDecorator wiring · no default-only list  
- 실기: 길게 눌러 드래그 → 흰 플래시 없음 · drop 후 목록 유지  

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
