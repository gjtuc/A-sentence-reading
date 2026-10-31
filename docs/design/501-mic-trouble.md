# design/501 — 마이크가 안 열린 까닭을 나눠 말하기 (0.3.513)

## 왜

- 웹에서 크롬 마이크 권한이 이미 허용인데 말로 묻기가 "마이크를 쓸 수 있게 허용한 뒤 다시 눌러 주세요" 만 보였다.
  `getUserMedia` 가 실패하면 까닭과 상관없이 모두 "권한 없음" 으로 읽었기 때문이다. 크롬 마이크 설정 화면에 장치
  고르기 칸이 없었으니 마이크 자체가 없었을 가능성이 크다.

## 결정

- `ShadowMic.trouble` (`MicTrouble`): 브라우저 오류 이름으로 나눈다.
  - `NotAllowedError`·`SecurityError` → 막힘 (주소창 권한·Windows 마이크 허용 확인)
  - `NotFoundError`·`OverconstrainedError` → 마이크 없음 (마이크·이어폰 연결)
  - `NotReadableError`·`AbortError` → 켜지 못함 (다른 프로그램·Windows 허용 확인)
- 휴대폰은 거절만 알 수 있어 예전 문구 그대로다.
- 증거: `voice_ask_client` `mic_denied` / `mic_unavailable` / `mic_failed` 에 `trouble`.

## 시험

- `mobile/test/voice_ask_475_test.dart` — 오류 이름 나누기, 마이크가 없을 때 "허용" 문구가 나오지 않음.
