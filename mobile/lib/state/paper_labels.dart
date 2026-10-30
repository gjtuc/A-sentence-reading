/// design/490 — the title and kind a reader gave a paper.
///
/// One label per paper cache id: the title to show, the kind (paper, review,
/// general), when, and which device. An empty field means "as analysed". The
/// paper's own title stays untouched, so pairing, duplicate checks and read-done
/// title keys keep using it. Labels are kept on the device (signed out, offline)
/// and shared through `/api/paper-labels` when signed in. The newer label wins
/// and replaces the whole label, so clearing on the web clears the phone.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/spot_sync.dart' show spotDeviceId;

const int kPaperLabelTitleMax = 300;
const List<String> kPaperLabelKinds = ['paper', 'review', 'general'];

/// One line, single spaces, no control characters, at most 300 characters.
String cleanPaperLabelTitle(String raw) {
  final one = raw
      .replaceAll(RegExp(r'[\u0000-\u001f\u007f]'), ' ')
      .split(RegExp(r'\s+'))
      .where((w) => w.isNotEmpty)
      .join(' ');
  return one.length <= kPaperLabelTitleMax
      ? one
      : one.substring(0, kPaperLabelTitleMax).trimRight();
}

class PaperLabel {
  const PaperLabel({
    required this.at,
    required this.dev,
    this.title = '',
    this.kind = '',
  });

  final String at;
  final String dev;
  final String title;
  final String kind;

  bool get isEmpty => title.isEmpty && kind.isEmpty;

  DateTime? get time => DateTime.tryParse(at);

  Map<String, Object?> toJson() => {
        'at': at,
        'dev': dev,
        if (title.isNotEmpty) 't': title,
        if (kind.isNotEmpty) 'k': kind,
      };

  static PaperLabel? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final at = raw['at'];
    final dev = raw['dev'];
    if (at is! String || DateTime.tryParse(at) == null) return null;
    final t = raw['t'];
    final k = raw['k'];
    return PaperLabel(
      at: at,
      dev: dev is String ? dev : '',
      title: t is String ? cleanPaperLabelTitle(t) : '',
      kind: k is String && kPaperLabelKinds.contains(k) ? k : '',
    );
  }

  bool isNewerThan(PaperLabel? other) {
    if (other == null) return true;
    final a = time;
    final b = other.time;
    if (a == null) return false;
    if (b == null) return true;
    return a.isAfter(b);
  }
}

abstract class PaperLabelTransport {
  Future<Map<String, Map<String, dynamic>>> all();
  Future<void> put(String cacheId, Map<String, Object?> label);
}

class PaperLabelStore extends ChangeNotifier {
  PaperLabelStore({
    this.transport,
    Future<String> Function()? deviceId,
    DateTime Function()? clock,
  })  : _deviceId = deviceId ?? spotDeviceId,
        _clock = clock ?? DateTime.now;

  PaperLabelTransport? transport;
  final Future<String> Function() _deviceId;
  final DateTime Function() _clock;

  final Map<String, PaperLabel> _labels = {};
  final Set<String> _unsent = {};
  String? _uid;
  Future<void>? _binding;

  static String prefsKey(String? uid) {
    final u = (uid ?? '').trim();
    return 'paper_labels_v1_${u.isEmpty ? 'anon' : u}';
  }

  /// The label in force for [cacheId], or null when the paper is as analysed.
  PaperLabel? labelFor(String cacheId) {
    final l = _labels[cacheId.trim()];
    return (l == null || l.isEmpty) ? null : l;
  }

  /// Load this account's labels (or the signed-out ones), then ask the server.
  Future<void> bindUid(String? uid) {
    final u = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    if (_binding != null && u == _uid) return _binding!;
    _uid = u;
    return _binding = () async {
      _labels.clear();
      _unsent.clear();
      await _load(u);
      if (_uid != u) return;
      notifyListeners();
      await pull();
    }();
  }

  /// Set both fields; an empty [title] or [kind] goes back to the analysed one.
  Future<void> set(String cacheId, {String title = '', String kind = ''}) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    _labels[cid] = PaperLabel(
      at: _clock().toUtc().toIso8601String(),
      dev: await _deviceId(),
      title: cleanPaperLabelTitle(title),
      kind: kPaperLabelKinds.contains(kind) ? kind : '',
    );
    _unsent.add(cid);
    notifyListeners();
    await _save();
    await _push();
  }

  /// Take newer labels from the server and send the ones it has not seen.
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
      final l = PaperLabel.fromJson(e.value);
      if (l == null) continue;
      final mine = _labels[e.key];
      if (l.isNewerThan(mine)) {
        _labels[e.key] = l;
        _unsent.remove(e.key);
        changed = true;
      } else if (mine != null && !mine.isNewerThan(l)) {
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
      final l = _labels[cid];
      if (l == null) {
        _unsent.remove(cid);
        continue;
      }
      try {
        await t.put(cid, l.toJson());
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
      final labels = obj['labels'];
      if (labels is Map) {
        for (final e in labels.entries) {
          final l = PaperLabel.fromJson(e.value);
          if (l != null) _labels['${e.key}'] = l;
        }
      }
      final unsent = obj['unsent'];
      if (unsent is List) {
        _unsent.addAll(unsent.whereType<String>().where(_labels.containsKey));
      }
    } catch (_) {}
  }

  Future<void> _save() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(
        prefsKey(_uid),
        jsonEncode({
          'labels': {for (final e in _labels.entries) e.key: e.value.toJson()},
          'unsent': _unsent.toList(),
        }),
      );
    } catch (_) {}
  }
}
