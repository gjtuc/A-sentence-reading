/// Saved pair for the import title switch. The other advisory cache stays empty.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';

const int kTitleSwitchSchema = 1;

class TitleSwitchEntry {
  const TitleSwitchEntry({
    required this.boxTitle,
    required this.verifiedTitle,
    required this.shown,
  });

  final String boxTitle;
  final String verifiedTitle;

  /// `box` or `verified`
  final String shown;

  String get displayed =>
      shown == 'verified' && verifiedTitle.trim().isNotEmpty
          ? verifiedTitle
          : boxTitle;
}

class TitleSwitchStore {
  TitleSwitchStore();

  String? _uid;
  final Map<String, TitleSwitchEntry> _mem = {};

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    _mem.clear();
  }

  String _key(String docUri, int sizeBytes, int lastModifiedMs) {
    final raw = '$sizeBytes|$lastModifiedMs|$docUri';
    return sha256.convert(utf8.encode(raw)).toString();
  }

  Future<File?> _file() async {
    final u = _uid;
    if (u == null || u.isEmpty) return null;
    final safe = u.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/title_switch/u_$safe');
    if (!await dir.exists()) await dir.create(recursive: true);
    return File('${dir.path}/index.json');
  }

  Future<Map<String, dynamic>> _read() async {
    final f = await _file();
    if (f == null || !await f.exists()) return {};
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is! Map) return {};
      if (raw['schema'] != kTitleSwitchSchema) return {};
      final rows = raw['rows'];
      if (rows is! Map) return {};
      return Map<String, dynamic>.from(rows);
    } catch (_) {
      return {};
    }
  }

  Future<void> _write(Map<String, dynamic> rows) async {
    final f = await _file();
    if (f == null) return;
    await f.writeAsString(
      jsonEncode({'schema': kTitleSwitchSchema, 'rows': rows}),
    );
  }

  Future<TitleSwitchEntry?> lookup({
    required String docUri,
    required int sizeBytes,
    required int lastModifiedMs,
  }) async {
    final key = _key(docUri, sizeBytes, lastModifiedMs);
    final mem = _mem[key];
    if (mem != null) return mem;
    final row = (await _read())[key];
    if (row is! Map) return null;
    final entry = TitleSwitchEntry(
      boxTitle: '${row['box'] ?? ''}',
      verifiedTitle: '${row['verified'] ?? ''}',
      shown: '${row['shown'] ?? 'box'}' == 'verified' ? 'verified' : 'box',
    );
    _mem[key] = entry;
    return entry;
  }

  Future<void> put({
    required String docUri,
    required int sizeBytes,
    required int lastModifiedMs,
    required String boxTitle,
    required String verifiedTitle,
    required String shown,
  }) async {
    final key = _key(docUri, sizeBytes, lastModifiedMs);
    final entry = TitleSwitchEntry(
      boxTitle: boxTitle,
      verifiedTitle: verifiedTitle,
      shown: shown == 'verified' && verifiedTitle.trim().isNotEmpty
          ? 'verified'
          : 'box',
    );
    _mem[key] = entry;
    final rows = await _read();
    rows[key] = {
      'box': entry.boxTitle,
      'verified': entry.verifiedTitle,
      'shown': entry.shown,
    };
    await _write(rows);
  }
}
