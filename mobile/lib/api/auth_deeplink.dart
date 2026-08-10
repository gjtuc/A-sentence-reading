/// design/77 — Android magic-link deep link → session (MethodChannel).
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

const String kAuthDeepLinkChannel = 'asr/auth_deeplink';

typedef MagicLinkHandler = void Function({String? token, String? error});

/// Listens for native VIEW intents with oauth/magic session.
class AuthDeepLinkBridge {
  AuthDeepLinkBridge({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel(kAuthDeepLinkChannel);

  final MethodChannel _channel;
  MagicLinkHandler? _handler;
  bool _listening = false;

  void setHandler(MagicLinkHandler? handler) {
    _handler = handler;
  }

  Future<void> start() async {
    if (_listening) return;
    _listening = true;
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'magicLinkResult') {
        final args = call.arguments;
        String? token;
        String? error;
        if (args is Map) {
          final t = '${args['token'] ?? ''}'.trim();
          final e = '${args['error'] ?? ''}'.trim();
          token = t.isEmpty ? null : t;
          error = e.isEmpty ? null : e;
        }
        _handler?.call(token: token, error: error);
      }
      return null;
    });
    // Cold start: intent may have landed before the handler was set.
    try {
      final raw = await _channel.invokeMethod<dynamic>('takePendingMagicSession');
      if (raw is Map) {
        final t = '${raw['token'] ?? ''}'.trim();
        final e = '${raw['error'] ?? ''}'.trim();
        if (t.isNotEmpty || e.isNotEmpty) {
          _handler?.call(
            token: t.isEmpty ? null : t,
            error: e.isEmpty ? null : e,
          );
        }
      }
    } catch (err) {
      debugPrint('auth deeplink pending: $err');
    }
  }
}
