# 98 — Draggable reader split bar

Modules: `mobile/lib/screens/reader_screen.dart`  
받침: [63](63-mobile-reader.md) · [97](97-reader-panel-expand.md)

## 무엇인가

문장/그림 사이 **분할 바를 위·아래로 드래그**해 비율 조절.  
기본 위치(60%) 근처 **자석 + 스마트 가이드**, 끝쪽 **텐션** 후 놓으면 문장만/그림만 전체 스냅 (97과 동일 모드).

| 포함 | 미포함 |
|------|--------|
| `_SplitHandle` · fraction 드래그 | 비율 prefs 저장 · 웹 |
| 기본값 자석 · 가이드 라인 | 커스텀 스냅 포인트 UI |
| 엣지 텐션 → full-panel snap | Live Enable / IPS |

## Product (locked this chip)

1. Drag divider to resize sentence/figure.  
2. Near default: magnet + visible guide.  
3. Near ends: slower drag; release snaps to text-only or figure-only.  
4. Double-tap expand (97) still works.

## Kill / rollback

- restore fixed 60/40 + plain Divider

## Version

**0.3.12** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
