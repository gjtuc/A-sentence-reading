/// design/187 D — archive cloud notes store on device (no revived notes UI).
library;

import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import 'evidence_bus.dart';
import 'figure_disk_cache.dart';

const String kNotesLocalArchiveDirName = 'asr_notes';

/// Persist notes `store_v2.json` under app documents; one-shot migrate + ack.
class NotesLocalArchive {
  NotesLocalArchive({this.rootResolver});

  final Future<Directory> Function()? rootResolver;

  String _uid = '';

  bool get isBound => _uid.isNotEmpty;

  String? get boundUid => _uid.isEmpty ? null : _uid;

  void bindUid(String? uid) {
    _uid = figureCacheSafeToken(uid ?? '', maxLen: 80);
  }

  String _migratedPrefsKey() {
    final u = _uid;
    if (u.isEmpty) return 'asr.notes.cloud_migrated.v1';
    return 'asr.notes.cloud_migrated.v1.u.$u';
  }

  Future<Directory> _docsRoot() async {
    if (rootResolver != null) return rootResolver!();
    return getApplicationDocumentsDirectory();
  }

  Future<File?> _storeFile() async {
    if (!isBound) return null;
    final docs = await _docsRoot();
    return File(
      p.join(docs.path, kNotesLocalArchiveDirName, 'u', _uid, 'store_v2.json'),
    );
  }

  Future<bool> saveStoreJson(Map<String, dynamic> store) async {
    final f = await _storeFile();
    if (f == null) return false;
    try {
      final parent = f.parent;
      if (!await parent.exists()) {
        await parent.create(recursive: true);
      }
      final part = File('${f.path}.part');
      await part.writeAsString(jsonEncode(store), flush: true);
      if (await f.exists()) {
        await f.delete();
      }
      await part.rename(f.path);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>?> loadStoreJson() async {
    final f = await _storeFile();
    if (f == null || !await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is Map<String, dynamic>) return raw;
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return null;
  }

  /// One-shot: GET /api/notes/sync → disk → ack → prefs migrated.
  Future<bool> migrateFromClient(
    AsrClient client, {
    required bool notesLocalSot,
  }) async {
    if (!notesLocalSot || !isBound) return false;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (prefs.getBool(_migratedPrefsKey()) == true) return true;

      asrEvidenceBus?.record(
        'notes_local_migrate_start',
        severity: 'lifecycle',
        ok: true,
      );

      final remote = await client.fetchNotesSync();
      if (remote.available && remote.store != null) {
        await saveStoreJson(remote.store!);
      } else {
        // EDGE: empty / unavailable — still archive an empty shell so wipe can proceed.
        await saveStoreJson(remote.store ?? const {'version': 2, 'papers': {}});
      }

      final acked = await client.ackNotesLocalMigrate();
      if (acked) {
        await prefs.setBool(_migratedPrefsKey(), true);
      }
      asrEvidenceBus?.record(
        'notes_local_migrate_done',
        severity: 'lifecycle',
        ok: acked,
      );
      return acked;
    } catch (_) {
      asrEvidenceBus?.record(
        'notes_local_migrate_done',
        severity: 'lifecycle',
        ok: false,
        code: 'exception',
      );
      return false;
    }
  }
}
