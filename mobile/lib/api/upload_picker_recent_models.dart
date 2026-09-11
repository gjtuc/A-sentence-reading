/// design/223 — uid-scoped recent PDF pick metadata (not durable URI reopen).
library;

import 'dart:convert';

const String kPickerRecentPrefsPrefix = 'asr.picker_recent.v1.u.';
const int kPickerRecentMaxItems = 30;

String pickerRecentPrefsKey(String uid) {
  final safe = uid.trim().replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
  if (safe.isEmpty) return '${kPickerRecentPrefsPrefix}anon';
  return '$kPickerRecentPrefsPrefix$safe';
}

class PickerRecentItem {
  PickerRecentItem({
    required this.contentHash,
    required this.displayName,
    this.label = '',
    this.uploadedAtMs = 0,
    this.source = 'saf',
  });

  final String contentHash;
  final String displayName;
  final String label;
  final int uploadedAtMs;
  final String source;

  Map<String, dynamic> toJson() => {
        'content_hash': contentHash,
        'display_name': displayName,
        'label': label,
        'uploaded_at_ms': uploadedAtMs,
        'source': source,
      };

  static PickerRecentItem? fromJson(Map<String, dynamic> m) {
    final hash = '${m['content_hash'] ?? ''}'.trim().toLowerCase();
    final name = '${m['display_name'] ?? ''}'.trim();
    if (hash.length != 64 || !RegExp(r'^[a-f0-9]{64}$').hasMatch(hash)) {
      return null;
    }
    if (name.isEmpty) return null;
    final at = m['uploaded_at_ms'] is num
        ? (m['uploaded_at_ms'] as num).toInt()
        : 0;
    var source = '${m['source'] ?? 'saf'}'.trim();
    if (source != 'saf' && source != 'recent' && source != 'queue') {
      source = 'saf';
    }
    return PickerRecentItem(
      contentHash: hash,
      displayName: name,
      label: '${m['label'] ?? ''}'.trim(),
      uploadedAtMs: at < 0 ? 0 : at,
      source: source,
    );
  }
}

class PickerRecentList {
  PickerRecentList({List<PickerRecentItem>? items})
      : items = List<PickerRecentItem>.unmodifiable(items ?? const []);

  final List<PickerRecentItem> items;

  bool get isEmpty => items.isEmpty;

  String encode() => jsonEncode({
        'v': 1,
        'items': items.map((e) => e.toJson()).toList(),
      });

  static PickerRecentList tryParse(String? raw) {
    if (raw == null || raw.trim().isEmpty) return PickerRecentList();
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return PickerRecentList();
      final list = decoded['items'];
      if (list is! List) return PickerRecentList();
      final out = <PickerRecentItem>[];
      final seen = <String>{};
      for (final row in list) {
        if (row is! Map) continue;
        final item = PickerRecentItem.fromJson(Map<String, dynamic>.from(row));
        if (item == null) continue;
        if (!seen.add(item.contentHash)) continue;
        out.add(item);
        if (out.length >= kPickerRecentMaxItems) break;
      }
      return PickerRecentList(items: out);
    } catch (_) {
      return PickerRecentList();
    }
  }
}
