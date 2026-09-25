/// Spoken form and its word symbols, kept on the phone between sessions.
///
/// The reading rules can change, so every row stores the speak-norm version it
/// was made with. A row from another version is dropped rather than drawn.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../practice_rhythm/follow_span.dart';

const String kSpokenDiskPrefsKey = 'asr_spoken_phones_v1';
const int kSpokenDiskMaxRows = 400;

class SpokenDiskRow {
  const SpokenDiskRow({
    required this.spoken,
    required this.spans,
  });

  final String spoken;
  final List<FollowSpan> spans;
}

Map<String, Object?> encodeSpokenRow(String spoken, List<FollowSpan> spans) => {
      's': spoken,
      'p': [
        for (final span in spans)
          {
            'a': span.start,
            'b': span.end,
            'w': span.weight,
            if (span.phone.isNotEmpty) 'f': span.phone,
          },
      ],
    };

SpokenDiskRow? decodeSpokenRow(Object? raw) {
  if (raw is! Map) return null;
  final spoken = '${raw['s'] ?? ''}';
  if (spoken.trim().isEmpty) return null;
  final list = raw['p'];
  final spans = <FollowSpan>[];
  if (list is List) {
    for (final item in list) {
      if (item is! Map) continue;
      final start = item['a'];
      final end = item['b'];
      final weight = item['w'];
      if (start is! num || end is! num || weight is! num) continue;
      spans.add(FollowSpan(
        start: start.toInt(),
        end: end.toInt(),
        weight: weight.toInt(),
        phone: '${item['f'] ?? ''}',
      ));
    }
  }
  return SpokenDiskRow(spoken: spoken, spans: spans);
}

/// Newest rows win when the store is over [kSpokenDiskMaxRows].
Map<String, Object?> trimSpokenRows(Map<String, Object?> rows) {
  if (rows.length <= kSpokenDiskMaxRows) return rows;
  final keys = rows.keys.toList();
  final drop = keys.length - kSpokenDiskMaxRows;
  final out = <String, Object?>{};
  for (var i = drop; i < keys.length; i++) {
    out[keys[i]] = rows[keys[i]];
  }
  return out;
}

class SpokenDiskCache {
  Map<String, Object?> _rows = {};
  bool _loaded = false;

  Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(kSpokenDiskPrefsKey);
      if (raw == null || raw.isEmpty) return;
      final decoded = jsonDecode(raw);
      if (decoded is Map) {
        _rows = decoded.map((k, v) => MapEntry('$k', v));
      }
    } catch (_) {
      _rows = {};
    }
  }

  SpokenDiskRow? peek(String key) => decodeSpokenRow(_rows[key]);

  Future<void> put(String key, String spoken, List<FollowSpan> spans) async {
    await load();
    _rows.remove(key);
    _rows[key] = encodeSpokenRow(spoken, spans);
    _rows = trimSpokenRows(_rows);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(kSpokenDiskPrefsKey, jsonEncode(_rows));
    } catch (_) {
      // EDGE: prefs full or unavailable — the in-memory cache still serves.
    }
  }
}
