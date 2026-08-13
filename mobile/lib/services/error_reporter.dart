/// design/130 — report client errors to cloud (admin triage).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../config.dart';
import 'hang_watchdog.dart';

/// Process-wide reporter (installed from [SentenceReadingApp]).
ErrorReporter? asrErrorReporter;
class ErrorReporter {
  ErrorReporter({
    required AsrClient client,
    HangWatchdog? hang,
  })  : _client = client,
        hang = hang ?? HangWatchdog();

  final AsrClient _client;
  final HangWatchdog hang;

  bool _installed = false;
  bool _enabled = true;
  bool _reporting = false;

  /// Call once from main() after WidgetsFlutterBinding.
  void install() {
    if (_installed) return;
    _installed = true;
    hang.setReporter(_reportHang);
    final prev = FlutterError.onError;
    FlutterError.onError = (details) {
      prev?.call(details);
      unawaited(
        report(
          kind: 'flutter_error',
          message: details.exceptionAsString(),
          stack: details.stack?.toString() ?? '',
          stage: 'flutter_error',
        ),
      );
    };
    PlatformDispatcher.instance.onError = (error, stack) {
      unawaited(
        report(
          kind: 'platform_error',
          message: error.toString(),
          stack: stack.toString(),
          stage: 'platform_error',
        ),
      );
      // false → let framework also see it; we still reported.
      return false;
    };
  }

  void setEnabled(bool enabled) => _enabled = enabled;

  Future<void> _reportHang({
    required String kind,
    required String message,
    String stage = '',
    String? paperTitle,
    String? cacheId,
  }) {
    return report(
      kind: kind,
      message: message,
      stage: stage,
      paperTitle: paperTitle,
      cacheId: cacheId,
    );
  }

  Future<void> report({
    required String kind,
    required String message,
    String stack = '',
    String stage = '',
    String? paperTitle,
    String? cacheId,
  }) async {
    if (!_enabled || _reporting) return;
    final msg = message.trim();
    if (msg.isEmpty) return;
    _reporting = true;
    try {
      await _client.reportError(
        kind: kind,
        message: msg,
        stack: stack,
        stage: stage,
        paperTitle: paperTitle,
        cacheId: cacheId,
        platform: defaultTargetPlatform.name,
        appVersion: kAppVersionLabel,
      );
    } catch (_) {
      // FAIL-CLOSED for UX: never surface report failures to the reader.
    } finally {
      _reporting = false;
    }
  }

  /// Report API failures without recursing on the report endpoint itself.
  Future<void> reportApiFailure(
    AsrApiException e, {
    required String stage,
    String? paperTitle,
    String? cacheId,
  }) {
    if (stage.contains('errors/report')) return Future.value();
    return report(
      kind: 'api_error',
      message: 'HTTP ${e.statusCode ?? '?'}: ${e.message}',
      stage: stage,
      paperTitle: paperTitle,
      cacheId: cacheId,
    );
  }
}
