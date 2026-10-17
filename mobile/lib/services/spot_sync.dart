/// design/411 — share reading spots live between the devices of one account.
///
/// A move here is sent after a short pause ([SpotSync.noteLocal]); every few
/// seconds [SpotSync.poll] asks the server what changed since the last answer and
/// hands spots read on other devices to [SpotSync.onRemote]. A spot is numbers
/// only: paper cache id, sentence index, figure index, time, device id.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:shared_preferences/shared_preferences.dart';

typedef SpotPage = ({int rev, Map<String, Map<String, dynamic>> spots});

abstract class SpotTransport {
  Future<SpotPage> since(int rev);
  Future<void> put(String cacheId, Map<String, Object?> spot);
}

typedef RemoteSpotHandler = Future<void> Function(
  String cacheId,
  int sentenceIndex,
  int figureIndex,
  String at,
);

const Duration kSpotDebounce = Duration(milliseconds: 600);
const Duration kSpotPoll = Duration(seconds: 3);

/// After this many failed calls in a row, poll only every [kSpotSlowPoll].
const int kSpotSlowAfter = 3;
const Duration kSpotSlowPoll = Duration(seconds: 60);

class SpotSync {
  SpotSync({
    required this.transport,
    required this.deviceId,
    required this.onRemote,
    this.onFailure,
    this.debounce = kSpotDebounce,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  final SpotTransport transport;
  final String deviceId;
  final RemoteSpotHandler onRemote;

  /// Called on the first failure of a streak with `put` / `poll`.
  final void Function(String stage, Object error)? onFailure;
  final Duration debounce;
  final DateTime Function() _clock;

  final Map<String, Map<String, Object?>> _pending = {};
  Timer? _flushTimer;
  int _rev = 0;
  bool _polling = false;
  bool _closed = false;
  int failures = 0;

  int get rev => _rev;

  bool get slow => failures >= kSpotSlowAfter;

  void noteLocal(String cacheId, int sentenceIndex, int figureIndex) {
    final cid = cacheId.trim();
    if (_closed || cid.isEmpty) return;
    _pending[cid] = {
      'si': sentenceIndex,
      'fi': figureIndex,
      'at': _clock().toUtc().toIso8601String(),
      'dev': deviceId,
    };
    _flushTimer?.cancel();
    _flushTimer = Timer(debounce, () => unawaited(flush()));
  }

  Future<void> flush() async {
    _flushTimer?.cancel();
    final rows = Map.of(_pending);
    _pending.clear();
    for (final e in rows.entries) {
      try {
        await transport.put(e.key, e.value);
        failures = 0;
      } catch (err) {
        _pending.putIfAbsent(e.key, () => e.value);
        _failed('put', err);
      }
    }
  }

  /// One round; returns how many spots from other devices were handed over.
  Future<int> poll() async {
    if (_closed || _polling) return 0;
    _polling = true;
    try {
      final page = await transport.since(_rev);
      failures = 0;
      var n = 0;
      for (final e in page.spots.entries) {
        final row = e.value;
        if (row['dev'] == deviceId) continue;
        // A move here that is not sent yet is newer than anything on the server.
        if (_pending.containsKey(e.key)) continue;
        final si = row['si'];
        final fi = row['fi'];
        final at = '${row['at'] ?? ''}';
        if (si is! int || fi is! int || at.isEmpty) continue;
        await onRemote(e.key, si, fi, at);
        n += 1;
      }
      _rev = math.max(_rev, page.rev);
      return n;
    } catch (err) {
      _failed('poll', err);
      return 0;
    } finally {
      _polling = false;
    }
  }

  void _failed(String stage, Object err) {
    failures += 1;
    if (failures == 1) onFailure?.call(stage, err);
  }

  void close() {
    _closed = true;
    _flushTimer?.cancel();
  }
}

const String kSpotDeviceKey = 'spot_device_id_v1';

/// A random id kept for this install, so a device skips its own spots.
Future<String> spotDeviceId() async {
  final p = await SharedPreferences.getInstance();
  final held = p.getString(kSpotDeviceKey) ?? '';
  if (held.length >= 8) return held;
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  final rnd = math.Random.secure();
  final id = List.generate(20, (_) => chars[rnd.nextInt(chars.length)]).join();
  await p.setString(kSpotDeviceKey, id);
  return id;
}
