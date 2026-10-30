# design/495 — 논문 전송 도우미: 설치 파일, 논문 사본 보관, 설정 칸 (0.3.508)

## 왜

- design/451 의 USB 도우미는 파이썬과 스크립트가 있어야 켜졌다. 처음 쓰는 사람에게는 너무 어렵다.
- 웹은 받은 논문을 브라우저 저장소에만 둔다. 브라우저 기록(사이트 데이터)을 지우면 그 컴퓨터의 논문이 사라진다.
  design/494 이후 휴대폰이 받아 가지 않은 서버 사본은 30일 뒤 지워진다.
- 경고 창이나 논문마다 표시는 넣지 않는다 (사용자 결정). 도우미는 설정에만 조용히 둔다.

## 무엇

### 도우미 실행 파일 (`scripts/helper_app.py` → `SentenceReadingHelper.exe`)

- PyInstaller 한 파일 (`scripts/build_helper_exe.py`). 파이썬 없이 돈다. 콘솔 창 없음.
- 아무 데서나 두 번 누르면:
  - `%LOCALAPPDATA%\SentenceReading\helper\` 로 자기를 복사하고,
  - `HKCU\...\Run` 으로 컴퓨터를 켤 때 켜지고,
  - `HKCU\...\Uninstall` 로 Windows 설정 > 앱에 "논문 전송 도우미 (문장 읽기)" 로 보이고,
  - 설치한 쪽을 켜고 "설치했어요" 창을 띄운다.
  - 이미 켜진 도우미는 `GET /store` + `X-Helper-Quit: 1` (Origin 없음) 로 끄고 바꾼다. no-cors 페이지 요청은 이 머리글을 못 붙인다.
- 설치된 쪽은 도우미를 돌린다. 이 컴퓨터에 adb 가 없으면 Google 의 `platform-tools-latest-windows.zip` 에서 `adb.exe` 와 DLL 둘만 받아 둔다 (실패하면 10분 뒤 다시). 받는 동안에도 웹 보관은 된다.
- `--uninstall`: 끄고, 등록을 지우고, 프로그램 폴더를 지운다. 보관한 논문 사본은 남긴다.
- 기록: `%LOCALAPPDATA%\SentenceReading\helper\helper.log` (1MB 에서 비움).

### 보관함 (`scripts/helper_store.py`, 같은 47815 포트의 `/store`)

- 경로 `%LOCALAPPDATA%\SentenceReading\helper-papers\{계정 키}\` (계정 키 = uid 의 sha256 앞 32자, `helperAccountKey`).
- 요청: `list`, `put_file`(뒤에 바이너리 하나), `put_done`, `get_file`(답 뒤에 바이너리 하나), `forget`, `progress`, `put_progress`.
- `put_done` 은 받은 파일을 다 확인한 뒤 통째로 바꿔 끼운다. 그 논문의 지운 기록은 없앤다.
- `forget` 은 지운 시각을 기억하고, 그 전에 저장된 사본만 지운다.
- Origin 은 `https://asr-sentence-reading*.run.app` 과 localhost 만 (다른 `*.run.app` 사이트는 사본을 못 읽는다). 기존 `/` 길(USB 중계)은 그대로.
- 휴대폰 확인 포트 47817: 접속하면 hello 한 줄을 주고 닫는다. 도우미가 47816 과 함께 `adb reverse` 를 건다.

### 웹 (`mobile/lib/services/helper_store*.dart`)

- `HelperMirror.run()` 한 번에 (design/450 규칙과 같다):
  1. 다른 브라우저에서 지운 논문: 이 브라우저가 그 뒤에 다시 받은 것이 아니면 여기서도 지운다 (`forgetFromNear`).
  2. 여기서 지운 논문: 도우미에 알린다 (그 전에 저장된 사본이 지워진다).
  3. 도우미에 없는(또는 더 옛) 논문을 보낸다. 20초 되돌리기 중인 논문은 뺀다.
  4. 여기 없는 논문을 도우미에서 되살린다.
  5. 읽던 자리: 도우미 것을 합치고, 합친 것을 다시 보낸다.
- 목록을 새로 받거나 지운 뒤 3초에 돈다 (`HelperMirrorRunner`, 한 번에 하나, 도중 바뀌면 한 번 더). 되살린 것이 있으면 목록을 다시 읽는다.
- 조용히: Chrome/Edge 는 127.0.0.1 에 붙을 때 "로컬 네트워크의 기기" 권한을 묻는다. 그래서 스스로는
  - 권한이 이미 허용이면,
  - 그런 권한이 없는 브라우저(Chromium 이 아님)이면,
  - 이 브라우저가 도우미를 만났거나 사용자가 안내를 열었으면 (`asr_helper_seen`)
  만 붙어 본다. 브라우저 데이터를 지워도 사이트 권한은 남아서, 허용해 둔 사람은 되살리기가 된다.
- 처음 한 번 `navigator.storage.persist()` 를 부탁한다 (디스크가 차도 지우지 말라고). Firefox 는 묻는 창이 떠서 건너뛴다.
- 증거 `helper_mirror_done` (sent / restored / dropped_here / dropped_there / failed / progress_merged / elapsed_ms, 실패 때 error).

### 설정 (`mobile/lib/widgets/helper_settings_tile.dart`, APK 칸 바로 아래, 늘 보임)

- 웹: 제목 "논문 전송 도우미", ①(USB 로 바로 옮김), ②(브라우저 기록을 지우면 지워지고, 도우미가 있으면 돌아옴), "없어도 동기화는 돼요", [도우미 받기] → 설치 안내 ①–⑤ 와 [파일 받기] (`/api/helper/download`).
- 휴대폰: ①, "없어도", USB 디버깅 켜짐/꺼짐, [USB 디버깅 켜는 법] → ①–③ 과 [개발자 설정 열기] (개발자 설정이 꺼져 있으면 휴대폰 정보, `asr/usb_debug` 채널).
- 초록 체크 "도우미 연결됨" 은 도우미가 답할 때만 (웹 `/store`, 휴대폰 47817).

### 서버와 배포

- `GET /api/helper/download`: GCS `{prefix}/mobile/sentence-reading-helper.exe` 를 흘려 보낸다. 없으면 "아직 준비되지 않았어요" 쪽.
- `/api/status` `helper_download_url`.
- click 02: 폰 설치 뒤 `scripts/build_helper_exe.py` (도우미 소스가 지난번 올린 것과 같으면 건너뜀, `click/out/helper_uploaded.txt`).

## 모르는 것

- 서명하지 않은 exe 라 Windows SmartScreen 과 브라우저가 경고한다. 안내 ② 에 넘어가는 법을 적었다.
- 휴대폰 USB 드라이버가 Windows 에 없는 기종은 adb 가 휴대폰을 못 본다. 그때도 웹 보관은 된다.

## 시험

- `tests/test_design_495_helper_store.py` (보관·지운 기록·다른 사이트 막기·확인 포트·끄기·adb 받기)
- `mobile/test/helper_mirror_495_test.dart` (처음 보내기, 지운 브라우저 되살리기, 지우기 양쪽, 다시 받은 논문, 되돌리기 중, 실행기, 계정 키, 문구와 연결)
