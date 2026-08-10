/// Background upload notification host (design/74 · 76).
///
/// Android: MethodChannel → UploadForegroundService + WorkManager schedule.
/// Tests / non-Android: [NoopUploadNotify].
/// INVARIANT: notification text never includes emails, tokens, or file paths.
/// INVARIANT: WorkManager input never carries session tokens (prefs only).
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String kPendingOpenCacheIdKey = 'asr.upload.pending_open_cache_id.v1';
const String kUploadNotifyChannel = 'asr/upload_notify';

/// Same content_hash dismissed battery guidance (design/76 product 3).
const String kBatteryHintDismissedHashKey =
    'asr.upload.battery_hint_dismissed.hash.v1';

/// Result of trying to start the foreground upload notification.
class UploadNotifyStart {
  const UploadNotifyStart({
    required this.active,
    this.permissionDeniedHint = false,
  });

  final bool active;

  /// Product 3A: upload continues; UI should warn background may stop.
  final bool permissionDeniedHint;
}

abstract class UploadNotify {
  Future<void> init();

  Future<UploadNotifyStart> startUploading({required String stage});

  Future<void> updateProgress({
    required int percent,
    required String stage,
  });

  Future<void> showCompleted({required String cacheId});

  Future<void> showFailed({required String message});

  /// design/75 — honest stall (not success). Tap should foreground the app.
  Future<void> showInterrupted({required String stage});

  Future<void> stop();

  void setOpenCacheIdHandler(void Function(String cacheId)? handler);

  Future<String?> takePendingOpenCacheId();

  /// design/76 — schedule unique WorkManager resume (KEEP delayed / REPLACE now).
  Future<bool> scheduleUploadResume({required bool immediate});

  /// Cancel pending/running unique resume work.
  Future<void> cancelUploadResume();

  /// True when OS battery optimize will not restrict the app.
  Future<bool> isIgnoringBatteryOptimizations();

  /// Open battery / app settings. Returns false if the intent could not start.
  Future<bool> openBatterySettings();
}

/// Test / desktop stub.
class NoopUploadNotify implements UploadNotify {
  void Function(String cacheId)? _handler;
  bool scheduled = false;

  @override
  Future<void> init() async {}

  @override
  Future<UploadNotifyStart> startUploading({required String stage}) async {
    return const UploadNotifyStart(active: false);
  }

  @override
  Future<void> updateProgress({
    required int percent,
    required String stage,
  }) async {}

  @override
  Future<void> showCompleted({required String cacheId}) async {
    final id = cacheId.trim();
    if (id.isEmpty) return;
    final p = await SharedPreferences.getInstance();
    await p.setString(kPendingOpenCacheIdKey, id);
  }

  @override
  Future<void> showFailed({required String message}) async {}

  @override
  Future<void> showInterrupted({required String stage}) async {}

  @override
  Future<void> stop() async {}

  @override
  void setOpenCacheIdHandler(void Function(String cacheId)? handler) {
    _handler = handler;
  }

  @override
  Future<String?> takePendingOpenCacheId() async {
    final p = await SharedPreferences.getInstance();
    final id = (p.getString(kPendingOpenCacheIdKey) ?? '').trim();
    await p.remove(kPendingOpenCacheIdKey);
    if (id.isEmpty) return null;
    _handler?.call(id);
    return id;
  }

  @override
  Future<bool> scheduleUploadResume({required bool immediate}) async {
    scheduled = true;
    return true;
  }

  @override
  Future<void> cancelUploadResume() async {
    scheduled = false;
  }

  @override
  Future<bool> isIgnoringBatteryOptimizations() async => true;

  @override
  Future<bool> openBatterySettings() async => false;
}

/// Production Android notifier via platform channel.
class ChannelUploadNotify implements UploadNotify {
  ChannelUploadNotify({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel(kUploadNotifyChannel);

  final MethodChannel _channel;
  void Function(String cacheId)? _openHandler;
  bool _active = false;

  @override
  Future<void> init() async {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'openCacheId') {
        final args = call.arguments;
        String id = '';
        if (args is Map) {
          id = '${args['cacheId'] ?? ''}'.trim();
        }
        if (id.isEmpty) {
          id = (await takePendingOpenCacheId()) ?? '';
        } else {
          final p = await SharedPreferences.getInstance();
          await p.setString(kPendingOpenCacheIdKey, id);
        }
        if (id.isNotEmpty) {
          _openHandler?.call(id);
        }
      }
      return null;
    });
  }

  @override
  void setOpenCacheIdHandler(void Function(String cacheId)? handler) {
    _openHandler = handler;
  }

  @override
  Future<UploadNotifyStart> startUploading({required String stage}) async {
    if (!Platform.isAndroid) {
      return const UploadNotifyStart(active: false);
    }
    try {
      final raw = await _channel.invokeMethod<dynamic>('startUploadNotify', {
        'title': 'PDF 올리는 중',
        'text': sanitizeNotifyStage(stage),
      });
      if (raw is Map) {
        final active = raw['active'] == true;
        final hint = raw['permissionDeniedHint'] == true;
        _active = active;
        return UploadNotifyStart(
          active: active,
          permissionDeniedHint: hint,
        );
      }
    } catch (e) {
      debugPrint('upload notify start: $e');
    }
    return const UploadNotifyStart(
      active: false,
      permissionDeniedHint: true,
    );
  }

  @override
  Future<void> updateProgress({
    required int percent,
    required String stage,
  }) async {
    if (!_active || !Platform.isAndroid) return;
    final pct = percent.clamp(0, 100);
    try {
      await _channel.invokeMethod<void>('updateUploadNotify', {
        'title': 'PDF 올리는 중',
        'text': '${sanitizeNotifyStage(stage)} · $pct%',
      });
    } catch (_) {}
  }

  @override
  Future<void> showCompleted({required String cacheId}) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      await stop();
      return;
    }
    final p = await SharedPreferences.getInstance();
    await p.setString(kPendingOpenCacheIdKey, id);
    if (_active && Platform.isAndroid) {
      try {
        await _channel.invokeMethod<void>('updateUploadNotify', {
          'title': '업로드 완료',
          'text': '탭하면 읽기로 이동합니다',
          'cacheId': id,
        });
      } catch (_) {}
      // Auto-clear FG after a while if user never taps.
      unawaited(Future<void>.delayed(const Duration(seconds: 45), stop));
    }
  }

  @override
  Future<void> showFailed({required String message}) async {
    await stop();
  }

  @override
  Future<void> showInterrupted({required String stage}) async {
    // WHY: keep FG ongoing so tap returns to app; never claim completed.
    if (!_active || !Platform.isAndroid) return;
    try {
      await _channel.invokeMethod<void>('updateUploadNotify', {
        'title': '업로드 중단됨',
        'text': sanitizeNotifyStage(stage),
      });
    } catch (_) {}
  }

  @override
  Future<void> stop() async {
    if (!Platform.isAndroid) {
      _active = false;
      return;
    }
    try {
      await _channel.invokeMethod<void>('stopUploadNotify');
    } catch (_) {}
    _active = false;
  }

  @override
  Future<String?> takePendingOpenCacheId() async {
    // Prefer native pending (notification tap while Dart was cold).
    if (Platform.isAndroid) {
      try {
        final native = await _channel.invokeMethod<String>('takePendingOpenCacheId');
        final n = (native ?? '').trim();
        if (n.isNotEmpty) {
          final p = await SharedPreferences.getInstance();
          await p.remove(kPendingOpenCacheIdKey);
          return n;
        }
      } catch (_) {}
    }
    final p = await SharedPreferences.getInstance();
    final id = (p.getString(kPendingOpenCacheIdKey) ?? '').trim();
    await p.remove(kPendingOpenCacheIdKey);
    return id.isEmpty ? null : id;
  }

  @override
  Future<bool> scheduleUploadResume({required bool immediate}) async {
    if (!Platform.isAndroid) return false;
    try {
      final ok = await _channel.invokeMethod<dynamic>('scheduleUploadResume', {
        'immediate': immediate,
      });
      return ok == true;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> cancelUploadResume() async {
    if (!Platform.isAndroid) return;
    try {
      await _channel.invokeMethod<void>('cancelUploadResume');
    } catch (_) {}
  }

  @override
  Future<bool> isIgnoringBatteryOptimizations() async {
    if (!Platform.isAndroid) return true;
    try {
      final ok = await _channel.invokeMethod<dynamic>(
        'isIgnoringBatteryOptimizations',
      );
      return ok == true;
    } catch (_) {
      // EDGE: channel missing → do not nag battery button.
      return true;
    }
  }

  @override
  Future<bool> openBatterySettings() async {
    if (!Platform.isAndroid) return false;
    try {
      final ok = await _channel.invokeMethod<dynamic>('openBatterySettings');
      return ok == true;
    } catch (_) {
      return false;
    }
  }

  /// WHY: notification text must never carry email/path/token-shaped strings.
  static String sanitizeNotifyStage(String stage) {
    var s = stage.trim();
    if (s.isEmpty) s = '처리 중';
    if (s.length > 48) s = '${s.substring(0, 45)}…';
    if (s.contains('@') || s.contains('\\') || s.contains('/data/')) {
      return '처리 중';
    }
    return s;
  }
}

/// Factory: Android channel notify; elsewhere noop.
UploadNotify createUploadNotify() {
  if (kIsWeb) return NoopUploadNotify();
  try {
    if (Platform.isAndroid) return ChannelUploadNotify();
  } catch (_) {}
  return NoopUploadNotify();
}
