# 161 — Settings APK download row

Modules: `settings_screen.dart` · `app_version.dart` · `app.py` `/api/status` · `upload_mobile_apk.sh`  
받침: [140](140-mobile-mvp-backlog-split.md) · [48](48-flutter-android-platform.md) · [155](155-deploy-live-guard.md)

## Product (locked)

- 설정 스위치 3개 **아래** · 초대/관리자 **위**
- `/api/status` `version` vs `kAppVersionLabel` 비교
- 구버전 + `mobile_apk_url` → **APK 다운로드** (`url_launcher` · 자동 설치 아님)
- 최신 → `앱 x.x.x · 최신입니다` · 버튼 숨김
- GCS public: `asr/mobile/sentence-reading-latest.apk`

## Ship

1. `scripts/upload_mobile_apk.sh` after `flutter build apk`
2. `ASR_MOBILE_APK_URL` in deploy env-vars
3. Version bump · deploy · APK on device

## Version

**0.3.95**
