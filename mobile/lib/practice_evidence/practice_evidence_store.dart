/// design/209 — KILLED 0.3.211: no local queue, no capacity.
library;

import 'dart:io';

import 'package:path_provider/path_provider.dart';

class PracticeEvidenceStore {
  PracticeEvidenceStore({this.maxEvents = 5000});

  final int maxEvents;
  String? _uid;
  int _droppedLocal = 0;

  int get droppedLocal => _droppedLocal;

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim();
  }

  Future<Directory> _rootDir() async {
    final root = await getApplicationSupportDirectory();
    return Directory(
      '${root.path}${Platform.pathSeparator}practice_evidence',
    );
  }

  /// No-op — feature killed; never write queue events.
  Future<void> append(Map<String, dynamic> event) async {
    _ = event;
  }

  Future<int> pendingCount() async => 0;

  Future<List<Map<String, dynamic>>> peek(int limit) async {
    _ = limit;
    return const [];
  }

  Future<void> ack(int count) async {
    _ = count;
  }

  /// Wipe leftover device files from pre-kill builds.
  Future<void> clearAll() async {
    try {
      final dir = await _rootDir();
      if (await dir.exists()) {
        await dir.delete(recursive: true);
      }
    } catch (_) {
      // Best-effort wipe only.
    }
    _uid = null;
    _droppedLocal = 0;
  }
}
