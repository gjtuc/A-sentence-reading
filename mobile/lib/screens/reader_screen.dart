import 'package:flutter/material.dart';

/// Placeholder — sentence reader + EN TTS (design/33). Figure index stays independent of sentence index.
class ReaderScreen extends StatelessWidget {
  const ReaderScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Text(
          '읽기 (스캐폴드)\n\n'
          '문장 단위 표시 · 그림 인덱스 독립 · TTS는 영어(서버 합성).\n'
          'AI 채점·Live Enable·IPS는 이 앱 범위가 아닙니다.',
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
