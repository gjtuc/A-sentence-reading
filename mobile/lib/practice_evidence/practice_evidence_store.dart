/// design/209 — durable JSONL queue for practice cycle wide events.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

class PracticeEvidenceStore {
  PracticeEvidenceStore({this.maxEvents = 5000});

  final int maxEvents;
  String? _uid;
  File? _file;
  int _droppedLocal = 0;
  final _lock = _SerialLock();

  int get droppedLocal => _droppedLocal;

  Future<void> bindUid(String? uid) async {
    await _lock.run(() async {
      _uid = (uid ?? '').trim();
      _file = null;
    });
  }

  Future<File> _ensureFile() async {
    if (_file != null) return _file!;
    final root = await getApplicationSupportDirectory();
    final safe = (_uid == null || _uid!.isEmpty)
        ? 'anon'
        : _uid!.replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '_');
    final dir = Directory(
      '${root.path}${Platform.pathSeparator}practice_evidence'
      '${Platform.pathSeparator}v1'
      '${Platform.pathSeparator}$safe',
    );
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    _file = File('${dir.path}${Platform.pathSeparator}queue.jsonl');
    if (!await _file!.exists()) {
      await _file!.create();
    }
    return _file!;
  }

  Future<void> append(Map<String, dynamic> event) async {
    await _lock.run(() async {
      final f = await _ensureFile();
      await f.writeAsString(
        '${jsonEncode(event)}\n',
        mode: FileMode.append,
        flush: true,
      );
      await _trimLocked(f);
    });
  }

  Future<void> _trimLocked(File f) async {
    final lines = await _readLines(f);
    if (lines.length <= maxEvents) return;
    final drop = lines.length - maxEvents;
    _droppedLocal += drop;
    final kept = lines.sublist(drop);
    await f.writeAsString(
      kept.isEmpty ? '' : '${kept.join('\n')}\n',
      flush: true,
    );
  }

  Future<List<String>> _readLines(File f) async {
    if (!await f.exists()) return [];
    final raw = await f.readAsString();
    if (raw.trim().isEmpty) return [];
    return raw
        .split('\n')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
  }

  Future<int> pendingCount() async {
    return _lock.run(() async {
      final f = await _ensureFile();
      return (await _readLines(f)).length;
    });
  }

  /// Peek up to [limit] events without removing.
  Future<List<Map<String, dynamic>>> peek(int limit) async {
    return _lock.run(() async {
      final f = await _ensureFile();
      final lines = await _readLines(f);
      final n = limit < lines.length ? limit : lines.length;
      final out = <Map<String, dynamic>>[];
      for (var i = 0; i < n; i++) {
        try {
          final o = jsonDecode(lines[i]);
          if (o is Map<String, dynamic>) {
            out.add(o);
          } else if (o is Map) {
            out.add(Map<String, dynamic>.from(o));
          }
        } catch (_) {
          // skip bad line on ack path by counting
          out.add(<String, dynamic>{
            'kind': 'practice_cycle_wide',
            'source': 'mobile',
            'ok': false,
            'code': 'bad_line',
            'details': <String, Object?>{'schema_v': 1},
          });
        }
      }
      return out;
    });
  }

  Future<void> ack(int count) async {
    if (count <= 0) return;
    await _lock.run(() async {
      final f = await _ensureFile();
      final lines = await _readLines(f);
      if (lines.isEmpty) return;
      final drop = count > lines.length ? lines.length : count;
      final kept = lines.sublist(drop);
      await f.writeAsString(
        kept.isEmpty ? '' : '${kept.join('\n')}\n',
        flush: true,
      );
    });
  }
}

class _SerialLock {
  Future<void> _tail = Future.value();

  Future<T> run<T>(Future<T> Function() fn) {
    final c = Completer<T>();
    _tail = _tail.then((_) async {
      try {
        c.complete(await fn());
      } catch (e, st) {
        c.completeError(e, st);
      }
    });
    return c.future;
  }
}
