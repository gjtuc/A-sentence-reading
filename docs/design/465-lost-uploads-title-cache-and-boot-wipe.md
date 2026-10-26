# 465 — 파일 3개 중 2개가 사라짐: 제목 보관본 오인 + 시작 때 대기열 삭제

## 증상

웹에서 PDF 3개를 분석 의뢰했는데 보관함에는 1개만 새로 생기고 2개는 흔적이 없었다.
분석된 1개도 읽기 화면 "Body ⚠"(`high_body_ratio`, 소제목을 못 찾아 대부분 Body로 묶임)였다.

## 원인

1. **다른 논문을 같은 논문으로 착각 (서버).** 첫 논문의 제목이 줄바꿈된 화학식 조각
   "heptanedionato)nickel(II)"로 잘못 잡혔다. 두 번째 파일 본문 앞부분에도 같은 화합물 이름이
   있어서 `find_cached_by_text`(앞 14,000자 안에 제목 키가 있으면 같은 논문)가 첫 논문의
   보관본을 돌려줬다. 새 논문은 만들어지지 않았다.
2. **두 번째 창이 첫 창의 대기열을 지움 (앱).** `_syncPrefsFromAuth()`는 로그인이 아니면
   `clearAll()`을 부른다. 그런데 앱 시작 직후(`bootstrapping`)에도 사용자는 아직 null이라
   "로그아웃"으로 보고 대기열과 IndexedDB 파일을 지웠다. 웹은 창끼리 저장소를 같이 쓰므로
   새 창 하나가 다른 창의 올릴 파일을 지웠고, 펌프는 파일이 없는 항목을 조용히 뺐다.
3. **웹에서 auth/status가 느리면 로그아웃 처리.** 웹은 쿠키를 앱이 읽을 수 없어
   `hasToken`이 늘 false라, 서버 응답이 늦으면 "다시 연결" 대신 로그인 화면으로 갔다
   (그리고 2번처럼 지움).

## 고침

- 서버 `_try_cache_hit`: 같은 파일(content_hash 같음)이 아니면 보관본의 앞 문장들이
  새 파일 본문에 실제로 있는지(`opening_sentences_present`, 공백·기호 무시 48자 접두,
  앞 8문장 중 2개) 확인한다. 없으면 `cache_title_hit_rejected`를 남기고 새로 분석한다.
- 앱 `_syncPrefsFromAuth`: `bootstrapping` 또는 `sessionRestorePending`이면 지우지 않는다.
  진짜 로그아웃(서버가 401로 답함)일 때만 지운다.
- 앱 `_enterSessionRestorePending`: 웹에서는 쿠키가 없으면 서버가 바로 401을 주므로,
  응답이 늦은 경우는 세션이 있다고 보고 "다시 연결"을 띄운다.

## 시험

- `tests/test_design_465_cache_title_body_check.py`
- `tests/test_design_400_archive_needs_same_build.py` (같은 파일 조건으로 갱신)
- `mobile/test/boot_keeps_queue_465_test.dart`
