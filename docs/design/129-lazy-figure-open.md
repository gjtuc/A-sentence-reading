# 129 — Lazy figure open (sentences first · ±1 window)

Modules: `api/app.py` · `models.py` · `cache/paper_cache.py` · Flutter `client`/`library_controller`/`reading_models` · web `app.js`  
받침: [04](04-api-contract.md) · [63](63-mobile-reader.md) · [128](128-clip-column-width.md)

## 무엇인가

`/open`이 모든 그림 PNG를 data-URL로 실어 **수십 MB JSON**이 되면 폰이 타임아웃한다.  
**문장·캡션 메타만** 열고, 그림 바이트는 **지금 인덱스 ±1**만 별도 요청한다 (화질 다운스케일 없음).

| 포함 | 미포함 |
|------|--------|
| open 응답에서 `image_src` 비움 | 의도적 해상도 축소 |
| `GET …/figures/window?center=&span=1` | 캡션 말줄임 · 처리 취소 |
| 앱·웹: 열기 후 / 넘길 때 창 prefetch | rich-v12 추출 변경 |
| status `lazy_figure_open` | APK 자체 업데이트 |

## Product (locked)

1. 문장 먼저 · 그림은 필요할 때  
2. 성공: Ewbank **열림 + Table 1·2** 폰 확인  
3. 화질 유지  
4. Prefetch = **현재 + 바로 옆(±1)** 만  

## Kill / rollback

Revert PR · 클라가 `lazy_figure_open=false`면 옛 풀-임베드 open을 기대하지 말고 창 API 생략(빈 그림 표시).

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.45** · pipeline **rich-v12** (추출 불변)

## Follow-up in same chip

Open GCS refresh pulls **session.json only** (not all PNGs); ±1 window may pull
each missing figure from GCS on demand.

## Also

/open does not await KO backfill (deferred warning).
