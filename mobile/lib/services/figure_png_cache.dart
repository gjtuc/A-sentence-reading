/// Figure images kept on the phone so reopening a paper does not fetch again.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

import 'tts_audio_cache.dart' show ttsCacheEvictions;

const int kFigureCacheMaxBytes = 200 * 1024 * 1024;
const String kFigureCacheDirName = 'asr_figure_png';

/// Paper and figure name one file. Both come from our own ids, so only the
/// characters that are unsafe in a file name are replaced.
String figurePngName({required String cacheId, required String figureId}) {
  final safe = RegExp(r'[^A-Za-z0-9_-]');
  final cid = cacheId.trim().replaceAll(safe, '_');
  final fid = figureId.trim().replaceAll(safe, '_');
  if (cid.isEmpty || fid.isEmpty) return '';
  return '$cid.$fid.png';
}

class FigurePngCache {
  Directory? _dir;

  Future<Directory?> _root() async {
    if (_dir != null) return _dir;
    try {
      final base = await getApplicationSupportDirectory();
      final dir = Directory(
        '${base.path}${Platform.pathSeparator}$kFigureCacheDirName',
      );
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      _dir = dir;
      return dir;
    } catch (_) {
      return null;
    }
  }

  Future<Uint8List?> read(String name) async {
    if (name.isEmpty) return null;
    try {
      final dir = await _root();
      if (dir == null) return null;
      final file = File('${dir.path}${Platform.pathSeparator}$name');
      if (!await file.exists()) return null;
      final bytes = await file.readAsBytes();
      if (bytes.isEmpty) return null;
      try {
        await file.setLastModified(DateTime.now());
      } catch (_) {
        // EDGE: platform refuses the stamp.
      }
      return bytes;
    } catch (_) {
      return null;
    }
  }

  Future<void> write(String name, List<int> bytes) async {
    if (name.isEmpty || bytes.isEmpty) return;
    try {
      final dir = await _root();
      if (dir == null) return;
      await File('${dir.path}${Platform.pathSeparator}$name')
          .writeAsBytes(bytes, flush: false);
      await _sweep(dir);
    } catch (_) {
      // EDGE: no space — the caller already has the bytes.
    }
  }

  Future<void> _sweep(Directory dir) async {
    try {
      final files = <({String path, int bytes, int stampMs})>[];
      await for (final entry in dir.list()) {
        if (entry is! File) continue;
        final stat = await entry.stat();
        files.add((
          path: entry.path,
          bytes: stat.size,
          stampMs: stat.modified.millisecondsSinceEpoch,
        ));
      }
      final drop = ttsCacheEvictions(
        files: files,
        maxBytes: kFigureCacheMaxBytes,
      );
      for (final path in drop) {
        try {
          await File(path).delete();
        } catch (_) {
          // EDGE: already gone.
        }
      }
    } catch (_) {
      // EDGE: listing failed.
    }
  }
}
