# 47 — Flutter `mobile/` 스캐폴드 (MVP 1단계)

모듈: `mobile/` · 받침: [33-mobile-flutter.md](33-mobile-flutter.md)

## 무엇을

설계 33의 구현 순서 **1번**: 레포에 Flutter 앱 뼈대를 둔다.

| 포함 | 미포함 (후속) |
|------|----------------|
| `mobile/pubspec.yaml` · `lib/` 화면 골격 | 실기 로그인·보관 API 완성 |
| Cloud Run base URL · `/api/status` 클라이언트 스텁 | TTS 재생 · 쿠키 인증 완성 |
| 표시명 「문장 읽기」 · applicationId 문서화 | `flutter create` 로 채우는 `android/` 플랫폼 (SDK 필요) |
| Python 계약 테스트 | Play Store · iOS |

## 로컬에서 플랫폼 생성

이 PC에 Flutter SDK가 없을 수 있다. SDK 설치 후:

```bash
cd mobile
flutter create . --org com.gjtuc --project-name sentence_reading
flutter pub get
flutter run
# 또는
flutter build apk
```

이미 `lib/`·`pubspec.yaml`이 있으면 `flutter create .` 가 플랫폼 폴더만 보강한다.

## 비목표

- Live Enable / IPS — **Trading Gate. ASR 밖**
- 앱에 Gemini/GCS secret 넣기 (**금지**)
- iOS

## 불변

- 문장↔그림 인덱스 독립
- AI 채점 없음
- TTS = 영어 (서버 합성)

## 버전

출시 **0.2.55** · status `mobile_flutter_scaffold: true` (이후 앱 버전은 후속 문서 참고)

## Version pin

Web/mobile **0.2.87** (invite redeem E2E · access session clear — see [67-access-gate.md](67-access-gate.md)).
