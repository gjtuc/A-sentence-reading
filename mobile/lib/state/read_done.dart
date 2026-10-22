/// design/442 — papers the reader marked as read to the end.
///
/// One mark per paper cache id: done or not, when, which device, and the PDF's
/// sha256 so the import list can mark the file too. Marks are kept on the device
/// (signed out, offline) and shared through `/api/read-done` when signed in. The
/// newer mark wins in both directions, so un-marking on the web clears the phone.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/spot_sync.dart' show spotDeviceId;

final _hex64 = RegExp(r'^[a-f0-9]{64}$');

class ReadDoneMark {
  const ReadDoneMark({
    required this.done,
    required this.at,
    required this.dev,
    this.hash = '',
  });

  final bool done;
  final String at;
  final String dev;
  final String hash;

  DateTime? get time => DateTime.tryParse(at);

  Map<String, Object?> toJson() => {
        'done': done,
        'at': at,
        'dev': dev,
        if (_hex64.hasMatch(hash)) 'h': hash,
      };

  static ReadDoneMark? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final done = raw['done'];
    final at = raw['at'];
    final dev = raw['dev'];
    if (done is! bool || at is! String || DateTime.tryParse(at) == null) {
      return null;
    }
    final h = raw['h'];
    return ReadDoneMark(
      done: done,
      at: at,
      dev: dev is String ? dev : '',
      hash: h is String && _hex64.hasMatch(h) ? h : '',
    );
  }

  bool isNewerThan(ReadDoneMark? other) {
    if (other == null) return true;
    final a = time;
    final b = other.time;
    if (a == null) return false;
    if (b == null) return true;
    return a.isAfter(b);
  }
}

abstract class ReadDoneTransport {
  Future<Map<String, Map<String, dynamic>>> all();
  Future<void> put(String cacheId, Map<String, Object?> mark);
}

class ReadDoneStore extends ChangeNotifier {
  ReadDoneStore({
    this.transport,
    Future<String> Function()? deviceId,
    DateTime Function()? clock,
  })  : _deviceId = deviceId ?? spotDeviceId,
        _clock = clock ?? DateTime.now;

  ReadDoneTransport? transport;
  final Future<String> Function() _deviceId;
  final DateTime Function() _clock;

  final Map<String, ReadDoneMark> _marks = {};
  final Set<String> _unsent = {};
  String? _uid;
  Future<void>? _binding;

  static String prefsKey(String? uid) {
    final u = (uid ?? '').trim();
    return 'read_done_v1_${u.isEmpty ? 'anon' : u}';
  }

  bool isDone(String cacheId) => _marks[cacheId.trim()]?.done ?? false;

  /// Hashes of the PDFs behind done papers, for the import list.
  Set<String> get doneHashes => {
        for (final m in _marks.values)
          if (m.done && m.hash.isNotEmpty) m.hash,
      };

  /// Load this account's marks (or the signed-out ones), then ask the server.
  Future<void> bindUid(String? uid) {
    final u = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    if (_binding != null && u == _uid) return _binding!;
    _uid = u;
    return _binding = () async {
      _marks.clear();
      _unsent.clear();
      await _load(u);
      if (_uid != u) return;
      notifyListeners();
      await pull();
    }();
  }

  Future<void> mark(String cacheId, {required bool done, String hash = ''}) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    final h = hash.trim().toLowerCase();
    final prev = _marks[cid];
    _marks[cid] = ReadDoneMark(
      done: done,
      at: _clock().toUtc().toIso8601String(),
      dev: await _deviceId(),
      hash: _hex64.hasMatch(h) ? h : (prev?.hash ?? ''),
    );
    _unsent.add(cid);
    notifyListeners();
    await _save();
    await _push();
  }

  /// Take newer marks from the server and send the ones it has not seen.
  Future<void> pull() async {
    final t = transport;
    if (t == null || _uid == null) return;
    final uid = _uid;
    Map<String, Map<String, dynamic>> remote;
    try {
      remote = await t.all();
    } catch (_) {
      return;
    }
    if (_uid != uid) return;
    var changed = false;
    for (final e in remote.entries) {
      final m = ReadDoneMark.fromJson(e.value);
      if (m == null) continue;
      final mine = _marks[e.key];
      if (m.isNewerThan(mine)) {
        _marks[e.key] = m;
        _unsent.remove(e.key);
        changed = true;
      } else if (mine != null && !mine.isNewerThan(m)) {
        _unsent.remove(e.key);
      }
    }
    if (changed) notifyListeners();
    await _save();
    await _push();
  }

  Future<void> _push() async {
    final t = transport;
    if (t == null || _uid == null || _unsent.isEmpty) return;
    for (final cid in _unsent.toList()) {
      final m = _marks[cid];
      if (m == null) {
        _unsent.remove(cid);
        continue;
      }
      try {
        await t.put(cid, m.toJson());
        _unsent.remove(cid);
      } catch (_) {
        break;
      }
    }
    await _save();
  }

  Future<void> _load(String? uid) async {
    try {
      final p = await SharedPreferences.getInstance();
      final raw = p.getString(prefsKey(uid));
      if (raw == null || raw.isEmpty) return;
      final obj = jsonDecode(raw);
      if (obj is! Map) return;
      final marks = obj['marks'];
      if (marks is Map) {
        for (final e in marks.entries) {
          final m = ReadDoneMark.fromJson(e.value);
          if (m != null) _marks['${e.key}'] = m;
        }
      }
      final unsent = obj['unsent'];
      if (unsent is List) {
        _unsent.addAll(unsent.whereType<String>().where(_marks.containsKey));
      }
    } catch (_) {}
  }

  Future<void> _save() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(
        prefsKey(_uid),
        jsonEncode({
          'marks': {for (final e in _marks.entries) e.key: e.value.toJson()},
          'unsent': _unsent.toList(),
        }),
      );
    } catch (_) {}
  }
}
