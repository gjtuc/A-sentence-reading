/// design/226 — Dart API for OPEN_DOCUMENT_TREE (asr/saf_tree).
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

const MethodChannel kSafTreeChannel = MethodChannel('asr/saf_tree');

class SafPdfHeadResult {
  const SafPdfHeadResult({
    required this.ok,
    required this.headText,
    required this.infoTitle,
    required this.pageCount,
    required this.truncated,
    required this.elapsedMs,
    required this.code,
  });

  final bool ok;
  final String headText;
  final String infoTitle;
  final int pageCount;
  final bool truncated;
  final int elapsedMs;
  final String code;
}

class SafTreePickResult {
  const SafTreePickResult({
    required this.treeUri,
    required this.displayLabel,
  });

  final String treeUri;
  final String displayLabel;
}

class SafTreePdfItem {
  const SafTreePdfItem({
    required this.docUri,
    required this.displayName,
    required this.sizeBytes,
    required this.lastModifiedMs,
  });

  final String docUri;
  final String displayName;
  final int sizeBytes;
  final int lastModifiedMs;
}

class SafTreeListResult {
  const SafTreeListResult({
    required this.items,
    required this.truncated,
  });

  final List<SafTreePdfItem> items;
  final bool truncated;
}

class SafTreeChannel {
  SafTreeChannel({MethodChannel? channel})
      : _channel = channel ?? kSafTreeChannel;

  final MethodChannel _channel;

  Future<SafTreePickResult?> pickTree({String? initialUri}) async {
    if (kIsWeb) return null;
    try {
      final raw = await _channel.invokeMethod<dynamic>(
        'pickTree',
        initialUri != null && initialUri.trim().isNotEmpty
            ? {'initialUri': initialUri.trim()}
            : null,
      );
      if (raw is! Map) return null;
      final uri = '${raw['treeUri'] ?? ''}'.trim();
      final label = '${raw['displayLabel'] ?? ''}'.trim();
      if (uri.isEmpty) return null;
      return SafTreePickResult(
        treeUri: uri,
        displayLabel: label.isEmpty ? '폴더' : label,
      );
    } on PlatformException {
      return null;
    }
  }

  /// design/238 — ACTION_OPEN_DOCUMENT (temp READ; optional multi PDF).
  Future<List<SafTreePdfItem>?> pickDocuments({
    bool multiple = true,
  }) async {
    if (kIsWeb) return null;
    try {
      final raw = await _channel.invokeMethod<dynamic>('pickDocuments', {
        'multiple': multiple,
      });
      if (raw == null) return null;
      if (raw is! List) return const [];
      final out = <SafTreePdfItem>[];
      for (final row in raw) {
        if (row is! Map) continue;
        final item = _pdfItemFromMap(row);
        if (item != null) out.add(item);
      }
      return out;
    } on PlatformException {
      return null;
    }
  }

  /// design/241 — tree write capability probe.
  Future<({bool writable, String code})> probeTreeWritable(String treeUri) async {
    final u = treeUri.trim();
    if (u.isEmpty || kIsWeb) {
      return (writable: false, code: 'unsupported');
    }
    try {
      final raw = await _channel.invokeMethod<dynamic>('probeTreeWritable', {
        'treeUri': u,
      });
      if (raw is! Map) return (writable: false, code: 'bad_map');
      return (
        writable: raw['writable'] == true,
        code: '${raw['code'] ?? ''}'.trim().isEmpty
            ? (raw['writable'] == true ? 'ok' : 'not_writable')
            : '${raw['code']}'.trim(),
      );
    } on PlatformException catch (e) {
      return (writable: false, code: e.code);
    } catch (_) {
      return (writable: false, code: 'exc');
    }
  }

  /// design/239 — Android Normalizer.NFKC when available; else null.
  Future<String?> normalizeNfkc(String text) async {
    if (kIsWeb) return null;
    try {
      final raw = await _channel.invokeMethod<dynamic>('normalizeNfkc', {
        'text': text,
      });
      if (raw is Map) {
        final out = '${raw['text'] ?? ''}';
        return out;
      }
      if (raw is String) return raw;
      return null;
    } catch (_) {
      return null;
    }
  }

  /// design/241 — stream-copy PDF into connected tree (collision rename).

  /// design/251 — write in-memory PDF bytes into connected tree.
  Future<SafTreePdfItem?> writeBytesIntoTree({
    required String treeUri,
    required String displayName,
    required List<int> bytes,
  }) async {
    final tree = treeUri.trim();
    final name = displayName.trim();
    if (tree.isEmpty || name.isEmpty || bytes.isEmpty || kIsWeb) return null;
    try {
      final raw = await _channel.invokeMethod<dynamic>('writeBytesIntoTree', {
        'treeUri': tree,
        'displayName': name,
        'bytes': bytes,
      });
      if (raw is! Map) return null;
      return _pdfItemFromMap(raw);
    } on PlatformException {
      rethrow;
    }
  }

  Future<SafTreePdfItem?> copyUriIntoTree({
    required String srcDocUri,
    required String treeUri,
    String? displayName,
  }) async {
    final src = srcDocUri.trim();
    final tree = treeUri.trim();
    if (src.isEmpty || tree.isEmpty || kIsWeb) return null;
    try {
      final raw = await _channel.invokeMethod<dynamic>('copyUriIntoTree', {
        'srcDocUri': src,
        'treeUri': tree,
        if (displayName != null && displayName.trim().isNotEmpty)
          'displayName': displayName.trim(),
      });
      if (raw is! Map) return null;
      return _pdfItemFromMap(raw);
    } on PlatformException {
      rethrow;
    }
  }

  SafTreePdfItem? _pdfItemFromMap(Map raw) {
    final docUri = '${raw['docUri'] ?? ''}'.trim();
    final name = '${raw['displayName'] ?? ''}'.trim();
    if (docUri.isEmpty || name.isEmpty) return null;
    final size = raw['sizeBytes'] is num ? (raw['sizeBytes'] as num).toInt() : 0;
    final mtime =
        raw['lastModifiedMs'] is num ? (raw['lastModifiedMs'] as num).toInt() : 0;
    return SafTreePdfItem(
      docUri: docUri,
      displayName: name,
      sizeBytes: size < 0 ? 0 : size,
      lastModifiedMs: mtime < 0 ? 0 : mtime,
    );
  }

  Future<bool> releaseTree(String treeUri) async {
    final u = treeUri.trim();
    if (u.isEmpty || kIsWeb) return false;
    try {
      final ok = await _channel.invokeMethod<dynamic>('releaseTree', {
        'treeUri': u,
      });
      return ok == true;
    } catch (_) {
      return false;
    }
  }

  Future<SafTreeListResult> listPdfs(
    String treeUri, {
    int maxItems = 500,
  }) async {
    final u = treeUri.trim();
    if (u.isEmpty || kIsWeb) {
      return const SafTreeListResult(items: [], truncated: false);
    }
    final raw = await _channel.invokeMethod<dynamic>('listPdfs', {
      'treeUri': u,
      'maxItems': maxItems,
    });
    if (raw is! Map) {
      return const SafTreeListResult(items: [], truncated: false);
    }
    final truncated = raw['truncated'] == true;
    final list = raw['items'];
    final out = <SafTreePdfItem>[];
    if (list is List) {
      for (final row in list) {
        if (row is! Map) continue;
        final item = _pdfItemFromMap(row);
        if (item != null) out.add(item);
      }
    }
    return SafTreeListResult(items: out, truncated: truncated);
  }

  Future<String?> sha256OfUri(String docUri) async {
    final u = docUri.trim();
    if (u.isEmpty || kIsWeb) return null;
    try {
      final hex = await _channel.invokeMethod<dynamic>('sha256OfUri', {
        'docUri': u,
      });
      final h = '$hex'.trim().toLowerCase();
      if (h.length != 64 || !RegExp(r'^[a-f0-9]{64}$').hasMatch(h)) {
        return null;
      }
      return h;
    } on PlatformException {
      return null;
    }
  }

  Future<Uint8List?> readPdfBytes(
    String docUri, {
    int maxBytes = 50 * 1024 * 1024,
  }) async {
    final u = docUri.trim();
    if (u.isEmpty || kIsWeb) return null;
    try {
      final raw = await _channel.invokeMethod<dynamic>('readPdfBytes', {
        'docUri': u,
        'maxBytes': maxBytes,
      });
      if (raw is Uint8List) return raw;
      if (raw is List<int>) return Uint8List.fromList(raw);
      return null;
    } on PlatformException catch (e) {
      if (e.code == 'too_large' || e.code == 'stale') rethrow;
      return null;
    }
  }

  /// design/228 · 231 — PdfBox head text + Info.Title (advisory).
  Future<SafPdfHeadResult> extractPdfHead(
    String docUri, {
    int maxChars = 8000,
    int maxPages = 2,
    int maxReadBytes = 50 * 1024 * 1024, // design/231 — match upload/read cap
  }) async {
    final u = docUri.trim();
    if (u.isEmpty || kIsWeb) {
      return const SafPdfHeadResult(
        ok: false,
        headText: '',
        infoTitle: '',
        pageCount: 0,
        truncated: false,
        elapsedMs: 0,
        code: 'unsupported',
      );
    }
    try {
      final raw = await _channel.invokeMethod<dynamic>('extractPdfHead', {
        'docUri': u,
        'maxChars': maxChars,
        'maxPages': maxPages,
        'maxReadBytes': maxReadBytes,
      });
      if (raw is! Map) {
        return const SafPdfHeadResult(
          ok: false,
          headText: '',
          infoTitle: '',
          pageCount: 0,
          truncated: false,
          elapsedMs: 0,
          code: 'bad_map',
        );
      }
      return SafPdfHeadResult(
        ok: raw['ok'] == true,
        headText: '${raw['headText'] ?? ''}',
        infoTitle: '${raw['infoTitle'] ?? ''}'.trim(),
        pageCount: raw['pageCount'] is num ? (raw['pageCount'] as num).toInt() : 0,
        truncated: raw['truncated'] == true,
        elapsedMs:
            raw['elapsedMs'] is num ? (raw['elapsedMs'] as num).toInt() : 0,
        code: '${raw['code'] ?? ''}'.trim(),
      );
    } on PlatformException catch (e) {
      return SafPdfHeadResult(
        ok: false,
        headText: '',
        infoTitle: '',
        pageCount: 0,
        truncated: false,
        elapsedMs: 0,
        code: e.code,
      );
    } catch (_) {
      return const SafPdfHeadResult(
        ok: false,
        headText: '',
        infoTitle: '',
        pageCount: 0,
        truncated: false,
        elapsedMs: 0,
        code: 'exc',
      );
    }
  }

  /// design/254 — DOCX head extract (word/document.xml + docProps/core.xml).
  Future<SafPdfHeadResult> extractDocxHead(
    String docUri, {
    int maxChars = 8000,
    int maxReadBytes = 50 * 1024 * 1024,
  }) async {
    final u = docUri.trim();
    if (u.isEmpty || kIsWeb) {
      return const SafPdfHeadResult(
        ok: false,
        headText: '',
        infoTitle: '',
        pageCount: 0,
        truncated: false,
        elapsedMs: 0,
        code: 'unsupported',
      );
    }
    try {
      final raw = await _channel.invokeMethod<dynamic>('extractDocxHead', {
        'docUri': u,
        'maxChars': maxChars,
        'maxReadBytes': maxReadBytes,
      });
      if (raw is! Map) {
        return const SafPdfHeadResult(
          ok: false,
          headText: '',
          infoTitle: '',
          pageCount: 0,
          truncated: false,
          elapsedMs: 0,
          code: 'bad_map',
        );
      }
      return SafPdfHeadResult(
        ok: raw['ok'] == true,
        headText: '${raw['headText'] ?? ''}',
        infoTitle: '${raw['infoTitle'] ?? ''}'.trim(),
        pageCount: raw['pageCount'] is num ? (raw['pageCount'] as num).toInt() : 1,
        truncated: raw['truncated'] == true,
        elapsedMs:
            raw['elapsedMs'] is num ? (raw['elapsedMs'] as num).toInt() : 0,
        code: '${raw['code'] ?? ''}'.trim(),
      );
    } on PlatformException catch (e) {
      return SafPdfHeadResult(
        ok: false,
        headText: '',
        infoTitle: '',
        pageCount: 0,
        truncated: false,
        elapsedMs: 0,
        code: e.code,
      );
    } catch (_) {
      return const SafPdfHeadResult(
        ok: false,
        headText: '',
        infoTitle: '',
        pageCount: 0,
        truncated: false,
        elapsedMs: 0,
        code: 'exc',
      );
    }
  }

  /// design/254 — delete document from SAF tree or downloads.
  Future<bool> deleteDocument(String docUri) async {
    final u = docUri.trim();
    if (u.isEmpty || kIsWeb) return false;
    try {
      final ok = await _channel.invokeMethod<dynamic>('deleteDocument', {
        'docUri': u,
      });
      return ok == true;
    } catch (_) {
      return false;
    }
  }
}
