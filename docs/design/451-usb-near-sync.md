# 451 — USB 선으로 동기화 (0.3.473)

## 문제

폰을 USB(디버깅 켬)로 PC에 꽂아 두었는데도 동기화가 서버를 거쳤다.
near sync(design/410)에는 USB 길이 없었다. WebRTC 직접 연결을 10초 기다리고, 안 되면 서버 중계로 갔다.

## 길

브라우저는 USB 기기를 직접 못 쓴다. 그래서 PC에 작은 도우미를 둔다: `scripts/usb_sync_bridge.py`.

- 웹 페이지 → 도우미: WebSocket `ws://127.0.0.1:47815`. 글자 = 제어 JSON, 바이너리 = 데이터.
- 폰 → 도우미: 폰의 `127.0.0.1:47816` 에 평범한 TCP. 도우미가 `adb reverse tcp:47816 tcp:47816` 으로 USB 선 너머 PC로 잇는다.
  앱은 암호 없는 HTTP를 막아 두었고(design/138, `network_security_config.xml` 는 그대로) WebSocket 은 HTTP 라서, 폰은 TCP 를 쓴다.
  틀: `[u32 길이][종류 1바이트][내용]`, 종류 0 = 제어 JSON, 1 = 데이터.
- 도우미는 접속하면 `{"t":"hello","cable":..,"web":..,"phone":..}` 를 보낸다. `cable` 은 `adb devices` 에 `device` 상태인 폰이 있다는 뜻이다.
  둘 다 오면 `{"t":"paired"}`. 그 뒤 데이터는 그대로 건넨다. 한쪽이 나가면 다른 쪽도 끊는다.
- 웹 페이지 Origin 은 `https://*.run.app` 과 localhost 만 받는다.
- 2초마다 `adb devices` 를 보고, 새로 꽂힌 폰에 `adb reverse` 를 건다(20초마다 다시 확인).

## 순서 (`NearLink`)

- 웹(`host`): 도우미에 먼저 붙어 본다(1.5초). 도우미가 폰이 꽂혔다고 하면 거기서 폰을 기다린다(3분). 아니면 지금까지처럼 서버 연결.
- 폰(`join`): 도우미에 먼저 붙어 본다. 웹이 이미 도우미에 있으면 USB. 아니면 서버의 열린 연결을 찾고, 있으면 그 길로. 없으면 도우미에서 웹을 기다린다.
- 진행 줄: "USB 선으로 옮기는 중". 증거 `near_sync_done` 에 `usb: 1`.

## 켜기

바탕화면 앱 아이콘(design/431, `hide_mouse_in_app.ahk`)이 앱과 함께 도우미를 `pythonw` 로 숨겨 켜고, 앱을 닫으면 끈다.
아이콘 없이 쓸 때는 `scripts/usb_sync_bridge.cmd`. 이미 켜져 있으면 두 번째 것은 포트가 차 있어 스스로 끝난다.
크롬이 "로컬 네트워크 기기" 권한을 물으면 허용해야 한다. 막으면 서버 길로 간다.

## 잰 것

실제 도우미로 12MB(양쪽 논문 3개)를 0.46초에 주고받았다 (PC 안, adb 없이).

## 시험

`mobile/test/near_usb_test.dart`, `tests/test_usb_sync_bridge.py`
