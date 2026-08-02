# 48 — Flutter Android 플랫폼 (`android/`)

모듈: `mobile/android/` · 받침: [33-mobile-flutter.md](33-mobile-flutter.md) · [47-flutter-scaffold.md](47-flutter-scaffold.md)

## 무엇을

설계 33 구현 순서 **2번**: `flutter create … --platforms=android` 로 네이티브 호스트를 레포에 둔다.

| 포함 | 미포함 (후속) |
|------|----------------|
| `mobile/android/` (Gradle · Manifest · MainActivity) | 로그인·보관·읽기·TTS 완성 |
| `applicationId` = `com.gjtuc.sentence_reading` | Play Store 서명 · CI APK |
| 런처 라벨 「문장 읽기」 · `INTERNET` (Cloud Run) | Android SDK 없는 PC에서 APK 바이너리 산출 보장 |
| status `mobile_android_platform` | iOS |

## 로컬에서 재생성 / APK

```bash
# Flutter SDK (이 PC 예: Desktop/.cursor/tools/flutter — 레포에 커밋하지 않음)
export PATH="$HOME/Desktop/.cursor/tools/flutter/bin:$PATH"
cd mobile
flutter create . --org com.gjtuc --project-name sentence_reading --platforms=android
flutter pub get
flutter analyze
# Android SDK + JDK 있을 때만:
flutter build apk
```

`android/local.properties` 는 기기별 경로 — **gitignore** (커밋 금지).

## 합격 (이번 단계)

- [x] `android/` 트리 · `applicationId` · 라벨 · MainActivity 패키지
- [x] Python 계약 테스트 · 웹 status 플래그
- [ ] 실기 사이드로드 APK (Android SDK 있는 환경)

## 비목표

- Live Enable / IPS — **Trading Gate. ASR 밖**
- 앱에 Gemini/GCS secret
- 인증·보관 API 완성 (33 순서 3)

## 버전

웹 **0.2.56** · `mobile_android_platform: true` · pubspec `0.2.56+1`

## Version pin

Web/mobile **0.2.84** (invite redeem E2E · access session clear — see [67-access-gate.md](67-access-gate.md)).
