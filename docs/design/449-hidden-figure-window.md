# 449 — 숨은 그림 창 때문에 그림 칸이 사라졌다 나타나던 것 (0.3.472)

## 문제

웹에서 문장과 그림을 같이 띄워 두면 몇 분마다 그림 칸과 경계선이 사라지고 몇 초 뒤 돌아왔다.
다른 '문장 읽기' 창(그림 창, `?pane=figure`, design/415)이 최소화되어 열려 있었다.
그림 창은 2초마다 hello 를 보내고, 원래 창은 5초 안에 hello 가 오면 그림 창이 열렸다고 보고 문장만 보인다.
크롬은 숨은 창의 타이머를 몇 분 뒤부터 1분에 한 번쯤으로 늦춘다. 그래서 hello 가 올 때마다 몇 초 동안 그림 칸이 빠졌다.

## 바꾼 것

- 그림 창은 `document.hidden` 이면 hello 에 `hidden: true` 를 붙인다 (`PaneLink.isHidden`, `paneWindowHidden`).
- 원래 창은 숨은 그림 창을 열린 것으로 세지 않는다. 기다리던 그림 창(`figureExpected`, design/424)이 숨은 채로 오면 기다림도 끝낸다. 그림은 원래 창에 남는다.
- 그림 창이 다시 보이면 `visibilitychange` 에서 바로 hello 를 보낸다 (`sayHello`). 그림이 곧바로 그쪽으로 옮겨 간다.

다른 창에 완전히 가려진 그림 창도 크롬은 숨은 것으로 본다. 그때도 그림은 원래 창에 남는다.

## 시험

`mobile/test/pane_hidden_test.dart`
