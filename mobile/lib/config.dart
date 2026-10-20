/// App-wide config for the 문장 읽기 Flutter client.
///
/// Secrets (Gemini, GCS, cookies) must never live here — only the public API origin.
library;

import 'package:flutter/foundation.dart' show kIsWeb;

/// Production Cloud Run base (no trailing slash).
/// design/138 — no dart-define API-base override (Live only; tests use [AsrConfig.overrideBaseUrl]).
const String kDefaultApiBaseUrl =
    'https://asr-sentence-reading-984608876300.asia-northeast3.run.app';

/// Fallback when [PackageInfo] is unavailable (error reports). Keep in sync with pubspec.
const String kAppVersionLabel = '0.3.459';

/// Runtime-overridable API settings (email session cookie in SessionStore).
class AsrConfig {
  AsrConfig({String? baseUrl}) : baseUrl = _normalize(baseUrl ?? kDefaultApiBaseUrl);

  final String baseUrl;

  /// For widget/unit tests that must not hit production.
  static String? overrideBaseUrl;

  static String _normalize(String url) {
    final t = url.trim();
    if (t.isEmpty) {
      throw ArgumentError('API base URL must not be empty');
    }
    return t.endsWith('/') ? t.substring(0, t.length - 1) : t;
  }

  /// Effective base: test override → web page origin → constructor → default.
  String get effectiveBaseUrl {
    if (overrideBaseUrl != null) return _normalize(overrideBaseUrl!);
    // design/405 — the server hosts the web app; its session cookie is same-origin.
    if (kIsWeb) return Uri.base.origin;
    return baseUrl;
  }
}
