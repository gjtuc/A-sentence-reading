package com.gjtuc.sentence_reading

import io.flutter.embedding.android.FlutterActivity

/**
 * WHY: Single FlutterActivity host for 「문장 읽기」.
 * Auth / library / reader / TTS stay in Dart (`lib/`); no Gemini/GCS secrets here.
 * Live Enable / IPS belong to Stock Trading Gate — not this app.
 */
class MainActivity : FlutterActivity()
