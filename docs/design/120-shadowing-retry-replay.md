# 120 — Shadowing: retry speak + replay my take

Modules: `shadowing_practice_screen.dart` · `shadowing_practice.js` · `index.html` · `app.js`  
받침: [82](82-shadowing-practice-loop.md) · [119](119-shadowing-chunks-build-failclosed.md)

## 무엇인가

연습 화면에서 현재 구간을 **말하기만 다시** 하거나, **방금 내가 말한 녹음**을 다시 듣는다.

| 포함 | 미포함 |
|------|--------|
| 「다시」= 말하기만 (첫 듣기 TTS 생략) | 청크 build / 같은 문장 점프 |
| 「다시 듣기」= 내 녹음 재생 | 보관·핀치·설정 카피 |
| 횟수 제한 없음 | Live Enable / IPS |
| 웹 + 앱 | |

## Product (locked)

1. 연습 화면 안 버튼  
2. 「다시」→ 말하기 사이클만 (듣기 TTS부터 다시 안 함)  
3. 「다시 듣기」→ **내가 녹음한** 마지막 take  
4. 녹음 없으면 「다시 듣기」는 실패 문구 (성공 위장 금지)  
5. 제한 없음  

## Kill / rollback

- `ASR_SHADOWING_PRACTICE=0`  
- Revert PR / 이전 APK  

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.34**
