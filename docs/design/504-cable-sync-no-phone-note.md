# design/504 — 휴대폰 없이 뜨던 자동 맞추기 실패 알림 (0.3.516)

## 왜

- 휴대폰을 꽂지 않았는데 웹에 "자동으로 맞추지 못했어요. 동기화 단추로 다시 해 주세요." 가 여러 번 떴다
  (2026-11-01 16:05–16:10, `near_sync_done` host `auto` `cancelled`, usb 0).
- 원인: 이 PC에서 돈 `flutter test` 는 `defaultTargetPlatform` 이 android 라서 `PhoneCableWatcher` 가 켜지고,
  127.0.0.1:47817 로 진짜 도우미에 닿는다. 웹이 /watch 중이라 `join()` 이 47816 에 붙고, 도우미는 웹에
  `{"t":"phone"}` 을 알린다. 시험은 곧 끝나고 웹은 40초 기다리다 실패 알림을 띄운다. click 02·01 도 시험을 돈다.
- 휴대폰을 꽂은 뒤의 자동 맞추기도 `closed` 로 끊겼다. 웹 창 두 개가 같이 /watch 를 들고 있어 둘 다
  `host()` 를 열고, 도우미는 나중 웹이 먼저 웹을 닫는다.

## 변경

- `cableAutoSyncHere` (helper_store): `FLUTTER_TEST` 환경에서는 거짓. `_startCableAutoSync` 가 시작하지 않는다.
- `NearLink.host()` 가 `auto` 일 때 도우미 hello 의 `cable`(adb `device` 상태 휴대폰)이 없으면 `no_cable` 로 바로 멈춘다.
  서버 링크를 만들지 않는다.
- `_autoNearSync` 는 단계가 `preparing` 을 넘은 뒤에만 "휴대폰과 맞추는 중…" 을 띄우고, 그 전에 멈추면 아무 말도
  하지 않는다.
- `runInOneWindow` (Web Locks `ifAvailable`): 한 브라우저의 창 여러 개 중 하나만 자동 맞추기를 한다. 휴대폰은 그냥 실행.
- 조사 맞춤법: "휴대폰와" → "휴대폰과".

## 시험

- `mobile/test/near_link_route_test.dart` — 케이블 없는 자동 host 는 preparing → failed, 서버 링크 0. 케이블 있으면 끝까지.
- `mobile/test/cable_auto_sync_496_test.dart` — 시험 중 `cableAutoSyncHere` 거짓, 한 창 실행, 문구.
