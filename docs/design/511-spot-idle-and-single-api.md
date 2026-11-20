# design/511 — 안 읽을 때는 위치 묻기를 멈추고, API 서버는 1대 (0.3.520)

## 확인한 것 (10월 27일 하루, 한국 시간)

- 사용자가 무언가 한 시간(PUT/PATCH/POST 가 있던 분): 139분.
- 요청이 있던 시간: 570분. 요청 14,510개 중 `GET /api/spots` 가 8,360개(62%). 휴대폰과 웹이 각각 8–9초마다 물었다 (`kSpotPoll` 3초 + 응답 시간).
- API 인스턴스가 켜진 시간: 1대 이상 939분, 2대 441분. 30일 합계 188시간.
- 과금은 인스턴스 기반(`cpu-throttling: false`)이다. 마지막 요청 뒤 최대 15분 기다린다. 앱이 화면에 떠 있기만 해도 3초마다 요청이 와서 인스턴스가 내려가지 않았다.
- 두 번째 인스턴스는 논문 분석(`ASR_INGEST_INLINE=1`)이 CPU 를 다 쓸 때(p99 98%) 생기고, 끝난 뒤 15분 남았다.

## 결정

- 위치 묻기: 터치·클릭, 휠, 키, 이 기기의 위치 이동(`persistOpenedProgress(publish)`, 연습 커서), 창·앱이 다시 선택됨(`AppLifecycleListener.onResume`)이 없으면 5분(`kSpotIdleStop`) 뒤 멈춘다. 다음 활동에서 바로 한 번 묻고 다시 3초 간격.
  - 입력은 `GestureBinding.pointerRouter` 전역 경로와 `HardwareKeyboard` 처리기로 본다. 다른 처리기를 막지 않는다(false 반환).
  - 마우스 움직임(hover)은 세지 않는다. 선택되지 않은 웹 창에도 들어오기 때문이다. 클릭·휠·키도 선택된 상태(`resumed`)일 때만 센다. 웹은 창 선택이 풀리면 `inactive`, 가려지면 `hidden` 이다 (Flutter web `app_lifecycle_state.dart`).
  - 묻기 자체는 원래부터 `resumed` 일 때만 보낸다. 백그라운드 앱과 선택되지 않은 웹 창은 묻지 않는다.
  - 바인딩이 없으면(단위 시험) 멈추지 않는다.
- API 최대 인스턴스 2 → 1 (`ASR_API_MAX_INSTANCES` 로 되돌린다). 워커는 2 그대로.

## 위험

- design/173b 는 분석 중에도 짧은 요청이 20초 안에 답하도록 서버를 키웠다. 1대면 분석 중 화면 요청이 늦어질 수 있다. 늦으면 `ASR_API_MAX_INSTANCES=2` 로 배포.
- 다른 기기에서 읽은 위치는 멈춰 있던 기기를 만지는 순간 따라온다. 그 전에는 따라오지 않는다.

## 시험

- `mobile/test/spot_sync_test.dart` 끝 — 5분, 멈춤, 입력 때 다시 시작, 입력 연결, 위치 이동·앱 복귀가 활동.
- `tests/test_scale_to_zero_395.py::test_max_instances_defaults_507_511`.