/// design/221 — durable multi-PDF upload reservation (not the active singleton draft).
library;

import 'dart:convert';

const String kUploadReservePrefsKey = 'asr.upload_reserve.v1';
const int kUploadReserveMaxItems = 20;

/// One reserved (or active-head) PDF waiting for serial ingest.
class UploadReserveItem {
  UploadReserveItem({
    required this.contentHash,
    required this.filename,
    this.localPath = '',
    this.bytesLen = 0,
    this.status = 'reserved',
    this.enqueuedAtMs = 0,
  });

  final String contentHash;
  final String filename;
  final String localPath;
  final int bytesLen;

  /// `reserved` | `active`
  final String status;
  final int enqueuedAtMs;

  bool get isActive => status == 'active';
  bool get isReserved => status == 'reserved';

  Map<String, dynamic> toJson() => {
        'content_hash': contentHash,
        'filename': filename,
        'local_path': localPath,
        'bytes_len': bytesLen,
        'status': status,
        'enqueued_at_ms': enqueuedAtMs,
      };

  static UploadReserveItem? fromJson(Map<String, dynamic> m) {
    final hash = '${m['content_hash'] ?? ''}'.trim().toLowerCase();
    final name = '${m['filename'] ?? ''}'.trim();
    if (hash.length != 64 || name.isEmpty) return null;
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hash)) return null;
    var status = '${m['status'] ?? 'reserved'}'.trim();
    if (status != 'reserved' && status != 'active') {
      status = 'reserved';
    }
    final len = m['bytes_len'] is num ? (m['bytes_len'] as num).toInt() : 0;
    final at = m['enqueued_at_ms'] is num
        ? (m['enqueued_at_ms'] as num).toInt()
        : 0;
    return UploadReserveItem(
      contentHash: hash,
      filename: name,
      localPath: '${m['local_path'] ?? ''}'.trim(),
      bytesLen: len < 0 ? 0 : len,
      status: status,
      enqueuedAtMs: at < 0 ? 0 : at,
    );
  }

  UploadReserveItem copyWith({
    String? localPath,
    String? status,
    int? bytesLen,
  }) {
    return UploadReserveItem(
      contentHash: contentHash,
      filename: filename,
      localPath: localPath ?? this.localPath,
      bytesLen: bytesLen ?? this.bytesLen,
      status: status ?? this.status,
      enqueuedAtMs: enqueuedAtMs,
    );
  }
}

class UploadReserveQueue {
  UploadReserveQueue({List<UploadReserveItem>? items})
      : items = List<UploadReserveItem>.unmodifiable(items ?? const []);

  final List<UploadReserveItem> items;

  int get length => items.length;
  bool get isEmpty => items.isEmpty;
  bool get isNotEmpty => items.isNotEmpty;

  UploadReserveItem? get head => items.isEmpty ? null : items.first;

  String encode() => jsonEncode({
        'v': 1,
        'items': items.map((e) => e.toJson()).toList(),
      });

  static UploadReserveQueue tryParse(String? raw) {
    if (raw == null || raw.trim().isEmpty) {
      return UploadReserveQueue();
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return UploadReserveQueue();
      final list = decoded['items'];
      if (list is! List) return UploadReserveQueue();
      final out = <UploadReserveItem>[];
      for (final row in list) {
        if (row is! Map) continue;
        final item = UploadReserveItem.fromJson(Map<String, dynamic>.from(row));
        if (item == null) continue;
        if (out.any((e) => e.contentHash == item.contentHash)) continue;
        out.add(item);
        if (out.length >= kUploadReserveMaxItems) break;
      }
      return UploadReserveQueue(items: out);
    } catch (_) {
      return UploadReserveQueue();
    }
  }
}
