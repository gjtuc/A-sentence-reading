import 'package:flutter/material.dart';

/// Placeholder — paper list from authenticated library API (design/33).
class LibraryScreen extends StatelessWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Text(
          '보관함 (스캐폴드)\n\n논문 목록·수집은 서버 API를 호출합니다. 로컬에 PDF를 두지 않는 것이 기본입니다.',
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
