# 125 — Caption-anchored figure extract (Fig/Table/Scheme)

Modules: `pdf/extract.py` · `llm/typography.py` (`PIPELINE_VERSION`)  
받침: [02](02-pdf-extract.md) · [92](92-figure-caption-order.md) · [124](124-missing-figures.md) · [44](44-compound-off.md)

## 무엇인가

PDF에 **캡션이 붙은** Fig. / Figure / Scheme / Table 은 캐러셀에 **빠짐없이** 들어와야 한다.  
지금은 이미지부터 찾고 아래 캡션을 붙이므로, 짝이 안 맞으면 번호가 통째로 사라진다.

| 포함 | 미포함 |
|------|--------|
| 캡션 먼저 스캔 → 근처 이미지/영역에 붙이기 (A) | compound 1a/1b 쪼개기 (명시적 비목표) |
| 캡션 위 그림·임베드 없음 시 페이지 클립 폴백 (B) | 캡션 말줄임 UI |
| pipeline `rich-v9` + 재분석으로 옛 보관본 갱신 | APK 자체 업데이트 |
| 앱+웹 (서버 추출 공통) | |

## Product (locked)

1. 재현: 현재 폰 논문(Fig 다수인데 일부만) → 다른 논문도  
2. 성공: 캡션에 Fig/Table/Scheme 라벨이 있는 항목이 **매칭되어 추출**  
3. A 후 필요 시 B (벡터·캡션 위·고아 캡션 클립)  
4. 로고 가끔 OK — **캡션 추적**이 본선  
5. 1a/1b 분해 안 함  
6. 계속 진행

## Kill / rollback

- Revert PR · `PIPELINE_VERSION` 되돌리면 옛 추출 경로로 복귀(재분석 전 캐시는 구버전 유지)

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.39** · pipeline **rich-v9**

Do not paste emails, cookies, tokens, or paper titles into chat/PR.
