import 'package:flutter/material.dart';

import 'screens/home_shell.dart';

/// Root Material app — brand title 「문장 읽기」.
class SentenceReadingApp extends StatelessWidget {
  const SentenceReadingApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '문장 읽기',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1B4F72)),
        useMaterial3: true,
      ),
      home: const HomeShell(),
    );
  }
}
