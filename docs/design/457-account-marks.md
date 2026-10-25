# 457 — 다 읽음·보관함 표시를 계정에, 논문 제목으로도 알아보기 (0.3.475)

## 바란 것

- 다 읽은 논문과 보관함에 있는 논문 표시가 웹에서도 보인다.
- 파일을 다시 받아도 (해시가 달라도) 제목이 같으면 「읽었던 논문」·「보관함에 있음」으로 안다.
- 다 읽음은 계정에 오래 남는다. 보관함 표시는 보관함에서 빠지면 없어진다.

## 제목 키

`paperTitleKey(title)` (`mobile/lib/pdf/paper_title_key.dart`) = `normalizePairingKey` 결과. 20자 이상, 3단어 이상일 때만, 300자까지.
짧은 제목이나 파일 이름이 제목으로 보이는 경우는 키가 없다 (`importEntryTitleKey`). SI 파일은 해시로만 맞춘다.

## 다 읽음

- 서버 `reading_done.py`: 표시에 `t` (제목 키)를 받는다. 같은 `at` 이면 빠진 `h`/`t` 를 채운다.
- 앱 `ReadDoneMark.title`. 보관함을 새로 받으면 `fillTitles` 로 예전 표시에도 제목을 붙여 보낸다.

## 보관함 표시

- 서버 `library_keys.py` + `GET/PUT /api/library-keys`: 기기마다 보관함 목록 (`{c, h, t}` 최대 3000개) 하나. 새 `at` 이면 통째로 바꾼다. 120일 안 온 기기는 지운다. GCS `users/{uid}/library_keys/keys.json`, generation CAS.
- 앱 `AccountLibraryKeys` (`mobile/lib/state/library_keys.dart`): 보관함 목록을 받은 뒤에만 내 목록을 올린다 (3초 debounce, 같은 내용이면 안 보냄). 다른 기기 목록만 표시에 쓴다.
- 보관함에서 지우면 다음 올릴 때 그 항목이 빠지므로 표시도 사라진다.

## 가져오기 화면

`PaperMarks` (해시 + 제목). 「보관함에 없는 것만」·「안 읽은 것만」과 줄 표시가 모두 이것을 쓴다. 세트는 둘 다 해시가 맞거나 메인 제목이 맞으면 보관함에 있다고 본다.

시험: `mobile/test/account_marks_457_test.dart`, `tests/test_design_457_library_keys.py`.
