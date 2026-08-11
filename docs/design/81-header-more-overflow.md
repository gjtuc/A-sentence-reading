# 81 — Header ⋯ menu overflow + shadowing kill on CD

## 무엇인가

클라우드에서 헤더 **⋯** 가 눌리지 않는 것처럼 보이던 원인:
`.app-header { overflow: hidden }` 이 드롭다운을 잘라 먹음.

또한 Cloud Run에 `ASR_SHADOWING_PRACTICE` 를 deploy env로 넣을 수 있게 함
(GitHub Actions variable).

## Version

**0.3.0**

## Live Enable / IPS

불필요.

## Kill

- `vars.ASR_SHADOWING_PRACTICE=1` → 라이브 킬 ON
- `0` / unset → OFF (코드 기본 fail-closed)
