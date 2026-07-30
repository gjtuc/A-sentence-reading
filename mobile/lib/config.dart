/// App-wide config for the 문장 읽기 Flutter client.
///
/// Secrets (Gemini, GCS, cookies) must never live here — only the public API origin.
library;

/// Production Cloud Run base (no trailing slash). Override in tests via [AsrConfig.overrideBaseUrl].
const String kDefaultApiBaseUrl =
    'https://asr-sentence-reading-984608876300.asia-northeast3.run.app';

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

  /// Effective base: test override → constructor → default.
  String get effectiveBaseUrl =>
      overrideBaseUrl != null ? _normalize(overrideBaseUrl!) : baseUrl;
}
