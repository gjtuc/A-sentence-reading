/// design/496 — with the PC helper and a USB cable, sync starts by itself.
///
/// The open web page holds the helper's /watch. The phone, while the app is on
/// screen, asks the helper's probe port every few seconds; when it answers and
/// says a web page is watching, the phone starts its side (`NearLink.join`).
/// The helper tells the page the moment the phone joins and the page starts its
/// side (`NearLink.host`). The sync button stays for everyone else.
library;

import 'dart:async';

import 'helper_store.dart';

/// Phone side: one sync per plug-in. Pulling the cable (two missed probes) or
/// coming back to the app after [again] allows the next one.
class PhoneCableWatcher {
  PhoneCableWatcher({
    required this.probe,
    required this.start,
    this.every = const Duration(seconds: 3),
    this.again = const Duration(minutes: 5),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final Future<Map<String, Object?>?> Function() probe;

  /// Runs one sync to its end.
  final Future<void> Function() start;
  final Duration every;
  final Duration again;
  final DateTime Function() _now;

  Timer? _timer;
  bool _done = false;
  bool _busy = false;
  int _misses = 0;
  DateTime? _lastAt;

  bool get running => _timer != null;

  void resume() {
    final last = _lastAt;
    if (last != null && _now().difference(last) >= again) _done = false;
    _timer?.cancel();
    _timer = Timer.periodic(every, (_) => unawaited(tick()));
    unawaited(tick());
  }

  void pause() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> tick() async {
    if (_busy) return;
    _busy = true;
    try {
      final hello = await probe();
      if (hello == null) {
        _misses += 1;
        if (_misses >= 2) _done = false;
        return;
      }
      _misses = 0;
      if (_done || hello['watch'] != true) return;
      _done = true;
      _lastAt = _now();
      await start();
    } catch (_) {
    } finally {
      _busy = false;
    }
  }
}

/// Web side: keep /watch open (retrying with a growing pause) and start a sync
/// when the helper says the phone is there.
class WebCableWatcher {
  WebCableWatcher({
    required this.open,
    required this.start,
    this.firstRetry = const Duration(seconds: 15),
    this.maxRetry = const Duration(minutes: 5),
  });

  final Future<HelperWatch?> Function() open;
  final Future<void> Function() start;
  final Duration firstRetry;
  final Duration maxRetry;

  Timer? _timer;
  HelperWatch? _watch;
  StreamSubscription<Map<String, Object?>>? _sub;
  Duration _wait = Duration.zero;
  bool _busy = false;
  bool _stopped = false;

  bool get connected => _watch != null;

  void begin() {
    _stopped = false;
    if (_watch != null || _timer != null) return;
    unawaited(_connect());
  }

  Future<void> _connect() async {
    _timer = null;
    if (_stopped) return;
    final w = await open();
    if (_stopped) {
      await w?.close();
      return;
    }
    if (w == null) {
      _retry();
      return;
    }
    _watch = w;
    _wait = Duration.zero;
    _sub = w.messages.listen(
      (m) {
        if (m['t'] == 'phone') _trigger();
      },
      onDone: _lost,
      onError: (Object _) => _lost(),
    );
    if (w.hello['phone'] == true) _trigger();
  }

  void _lost() {
    _watch = null;
    unawaited(_sub?.cancel());
    _sub = null;
    _retry();
  }

  void _retry() {
    if (_stopped) return;
    _wait = _wait == Duration.zero
        ? firstRetry
        : (_wait * 2 > maxRetry ? maxRetry : _wait * 2);
    _timer = Timer(_wait, () => unawaited(_connect()));
  }

  void _trigger() {
    if (_busy) return;
    _busy = true;
    start().whenComplete(() => _busy = false).ignore();
  }

  Future<void> stop() async {
    _stopped = true;
    _timer?.cancel();
    _timer = null;
    await _sub?.cancel();
    _sub = null;
    await _watch?.close();
    _watch = null;
  }
}
