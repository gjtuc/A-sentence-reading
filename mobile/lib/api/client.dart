/// Thin HTTP client for the existing Cloud Run FastAPI surface.
///
/// Scaffold: only [fetchStatus]. Login/library/reader calls land in later PRs.
///
/// WHY separate from UI: screens must not know cookie jars / timeouts; when auth
/// lands, cookie persistence stays in this layer (design/33).
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

/// Parsed `/api/status` JSON (subset used by the mobile shell).
class AsrStatus {
  AsrStatus({
    required this.ok,
    required this.version,
    required this.pipeline,
    this.mobileFlutterScaffold = false,
  });

  /// Tolerant parse: missing keys become empty strings / false — never throw on
  /// partial JSON (edge: older Cloud Run without `mobile_flutter_scaffold`).
  factory AsrStatus.fromJson(Map<String, dynamic> json) {
    return AsrStatus(
      ok: json['ok'] == true,
      version: '${json['version'] ?? ''}',
      pipeline: '${json['pipeline'] ?? json['pipeline_version'] ?? ''}',
      mobileFlutterScaffold: json['mobile_flutter_scaffold'] == true,
    );
  }

  final bool ok;
  final String version;
  final String pipeline;
  final bool mobileFlutterScaffold;
}

class AsrClient {
  AsrClient({AsrConfig? config, http.Client? httpClient})
      : _config = config ?? AsrConfig(),
        _http = httpClient ?? http.Client();

  final AsrConfig _config;
  final http.Client _http;

  Uri _uri(String path) {
    final p = path.startsWith('/') ? path : '/$path';
    return Uri.parse('${_config.effectiveBaseUrl}$p');
  }

  /// GET /api/status — health / version probe for the home shell.
  ///
  /// Throws [AsrApiException] on non-2xx or non-object JSON (edge: HTML error pages).
  Future<AsrStatus> fetchStatus() async {
    final res = await _http.get(_uri('/api/status')).timeout(const Duration(seconds: 20));
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw AsrApiException('status HTTP ${res.statusCode}', res.statusCode);
    }
    final body = jsonDecode(res.body);
    if (body is! Map<String, dynamic>) {
      throw AsrApiException('status body is not a JSON object', res.statusCode);
    }
    return AsrStatus.fromJson(body);
  }

  void close() => _http.close();
}

class AsrApiException implements Exception {
  AsrApiException(this.message, [this.statusCode]);

  final String message;
  final int? statusCode;

  @override
  String toString() => 'AsrApiException($message, status=$statusCode)';
}
