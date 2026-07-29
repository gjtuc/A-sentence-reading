import 'package:flutter/material.dart';

/// Placeholder — Google OAuth / session cookie against Cloud Run (design/33 step 2).
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Text(
          '로그인 화면 (스캐폴드)\n\n'
          '후속: Cloud Run 기존 인증과 동일한 세션을 모바일 WebView 또는 OAuth로 연결합니다.\n'
          '앱에 API 키·GCS 비밀을 넣지 않습니다.',
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
