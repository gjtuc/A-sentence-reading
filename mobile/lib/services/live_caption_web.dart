/// design/500 — the browser's SpeechRecognition (Chrome and Edge, prefixed as
/// webkitSpeechRecognition). It listens beside the recording; the caption is
/// never sent anywhere by the app.
library;

import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:web/web.dart' as web;

import 'live_caption.dart' show liveCaptionJoin;

/// A round that ends on its own (silence, Chrome's time limit) is restarted
/// this many times at most, so a recognizer that keeps failing cannot loop.
const int _kRounds = 40;

/// Errors after which another round cannot help.
const Set<String> _kFatal = {
  'not-allowed',
  'service-not-allowed',
  'audio-capture',
  'language-not-supported',
  'network',
};

JSFunction? _recognizer() {
  final w = web.window as JSObject;
  for (final name in const ['SpeechRecognition', 'webkitSpeechRecognition']) {
    final c = w[name];
    if (c != null && c.typeofEquals('function')) return c as JSFunction;
  }
  return null;
}

String _heard(JSObject event) {
  final results = event['results'] as JSObject?;
  if (results == null) return '';
  final n = (results['length'] as JSNumber?)?.toDartInt ?? 0;
  final parts = <String>[];
  for (var i = 0; i < n; i++) {
    final best = (results['$i'] as JSObject?)?['0'] as JSObject?;
    final text = (best?['transcript'] as JSString?)?.toDart ?? '';
    if (text.isNotEmpty) parts.add(text);
  }
  return parts.join(' ');
}

void Function()? start(void Function(String text) onText) {
  final make = _recognizer();
  if (make == null) return null;
  final JSObject rec;
  try {
    rec = make.callAsConstructor<JSObject>();
  } catch (_) {
    return null;
  }
  var stopped = false;
  var kept = '';
  var now = '';
  var rounds = 0;

  rec['lang'] = 'ko-KR'.toJS;
  rec['continuous'] = true.toJS;
  rec['interimResults'] = true.toJS;
  rec['onresult'] = ((JSObject e) {
    if (stopped) return;
    now = _heard(e);
    onText(liveCaptionJoin(kept, now));
  }).toJS;
  rec['onerror'] = ((JSObject e) {
    final code = (e['error'] as JSString?)?.toDart ?? '';
    if (_kFatal.contains(code)) stopped = true;
  }).toJS;
  rec['onend'] = ((JSObject _) {
    if (stopped || ++rounds > _kRounds) return;
    kept = liveCaptionJoin(kept, now);
    now = '';
    try {
      rec.callMethod<JSAny?>('start'.toJS);
    } catch (_) {
      stopped = true;
    }
  }).toJS;
  try {
    rec.callMethod<JSAny?>('start'.toJS);
  } catch (_) {
    return null;
  }
  return () {
    if (stopped) return;
    stopped = true;
    try {
      rec.callMethod<JSAny?>('abort'.toJS);
    } catch (_) {}
  };
}
