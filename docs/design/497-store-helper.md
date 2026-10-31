# design/497 — 논문 전송 도우미를 Microsoft Store 로 (0.3.510)

## 왜

- V3 가 design/495 의 도우미 exe 를 `Persistence/MDP.AutoRun.M224` (행위 진단) 로 지웠다.
  분석 보고서의 의심 행위: 자동 실행 등록(HKCU Run), PE 파일 생성(PyInstaller 한 파일이 실행마다 DLL 30여 개를 임시 폴더에 풂),
  자기 복제(LocalAppData 로 복사), 네트워크 연결. 클라우드 평판 사용자 수 0.
- 크롬 「의심스러운 파일 차단됨」, Windows 「PC 보호」 도 서명 없는 새 exe 라서 뜬다.
- Store MSIX 는 Microsoft 가 서명하고, 설치·자동 실행을 Windows 가 맡는다. 위 행위 중 셋이 사라진다.

## 무엇

### 도우미 (`scripts/helper_app.py`, `scripts/helper_window.py`)

- `is_packaged()` (GetCurrentPackageFullName) 이면 설치 단계(복사, Run 키, Uninstall 키)를 하나도 하지 않는다.
- `SentenceReadingHelperStartup.exe` (같은 exe 의 사본, 매니페스트 startup task 가 로그인 때 실행) 는 도우미만 돌린다. 이미 돌면 끝난다.
- 시작 메뉴의 `SentenceReadingHelper.exe` 는 도우미가 안 돌면 startup 사본을 띄우고, 작은 창을 연다.
  - 창: 켜짐, 휴대폰 USB 연결, 웹 페이지 열림, 보관한 논문 수, [보관 폴더 열기] [닫기]. 창을 닫아도 도우미는 남는다.
  - adb 가 없으면 「휴대폰 연결 도구 받기」 단추. Store 판은 누를 때만 받는다 (`adb_finder(auto=False)`).
  - 보관 폴더는 패키지 LocalCache 아래의 실제 경로로 연다 (`real_path`).
- 안부에 `adb` (None 모름 / True / False). 웹 설정은 False 면 "도우미 창에서 「휴대폰 연결 도구 받기」를 눌러 주세요."
- 패키지 밖(exe, `--run`) 동작은 design/495 그대로.

### 포장 (`scripts/build_helper_msix.py`)

- PyInstaller `--onedir` (실행마다 풀지 않음) + startup 사본 + 아이콘(Pillow) + `AppxManifest.xml` → `makeappx pack`.
- makeappx 는 NuGet `Microsoft.Windows.SDK.BuildTools` 를 `.cache/tools` 에 풀어 쓴다 (PC 에 설치 없음).
- 서명하지 않는다 (Store 가 서명). 결과: `click/out/SentenceReadingHelper.msix`.
- 버전: 앱 0.3.510 → 패키지 1.3.510.0.
- 매니페스트: `runFullTrust`, `internetClient`, `windows.startupTask` (Enabled), 최소 Windows 10 1809.
- 식별 값: `scripts/helper_msix_identity.json` (Partner Center > 제품 ID 의 패키지 이름, 게시자, 게시자 표시 이름). 지금은 자리표시 값.

### 서버·설정

- `GET /privacy`: 개인정보 처리방침 (Store 등록에 필요).
- `/api/status` `helper_store_url`: `mobile_apk_gcs.HELPER_STORE_ID` 가 차면 `https://apps.microsoft.com/detail/{id}` (`ASR_HELPER_STORE_URL` 로 덮어쓰기).
- 웹 설정 칸: Store 주소가 있으면 「스토어에서 받기」 와 Store 안내 ①–④, 없으면 지금의 파일 받기 안내.

## 남은 일

1. 사용자: Partner Center 계정, 이름 예약, 제품 ID 값 전달.
2. 식별 값을 넣고 다시 포장, Partner Center 에 msix 업로드 (개인정보 처리방침 주소 `/privacy`).
3. 등록되면 `HELPER_STORE_ID` 를 채워 배포.

## 시험

- `tests/test_design_497_store_helper.py` — 패키지 안에서 설치 안 함, startup 사본, 창 띄우기, adb 는 누를 때만, 안부 adb, 보관 폴더 경로, 창 문구, 매니페스트, 개인정보 페이지와 Store 주소.
- `mobile/test/cable_auto_sync_496_test.dart` 끝 — Store 안내 연결.
