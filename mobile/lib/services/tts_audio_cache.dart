/// Spoken audio kept on the phone so a repeat does not fetch it again.
///
/// Same sentence, voice, rate and reading-rule version means the same sound, so
/// those four make the file name. Random-voice mode draws a new voice each play,
/// so nothing is stored for it.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';

const int kTtsCacheMaxBytes = 120 * 1024 * 1024;
const String kTtsCacheDirName = 'asr_tts_audio';

String ttsAudioKey({
  required String text,
  required String voice,
  required double rate,
  required String speakNorm,
}) {
  final rounded = (rate * 100).round();
  final seed = '$speakNorm|$voice|$rounded|${text.trim()}';
  final digest = sha256.convert(utf8.encode(seed));
  return digest.toString().substring(0, 32);
}

/// Oldest files first, until the folder fits in [maxBytes].
List<String> ttsCacheEvictions({
  required List<({String path, int bytes, int stampMs})> files,
  int maxBytes = kTtsCacheMaxBytes,
}) {
  var total = 0;
  for (final f in files) {
    total += f.bytes;
  }
  if (total <= maxBytes) return const [];
  final sorted = [...files]..sort((a, b) => a.stampMs.compareTo(b.stampMs));
  final out = <String>[];
  for (final f in sorted) {
    if (total <= maxBytes) break;
    out.add(f.path);
    total -= f.bytes;
  }
  return out;
}

class TtsAudioCache {
  Directory? _dir;

  Future<Directory?> _root() async {
    if (_dir != null) return _dir;
    try {
      final base = await getApplicationSupportDirectory();
      final dir = Directory(
        '${base.path}${Platform.pathSeparator}$kTtsCacheDirName',
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

  Future<Uint8List?> read(String key) async {
    if (key.isEmpty) return null;
    try {
      final dir = await _root();
      if (dir == null) return null;
      final file = File('${dir.path}${Platform.pathSeparator}$key.mp3');
      if (!await file.exists()) return null;
      final bytes = await file.readAsBytes();
      if (bytes.isEmpty) return null;
      // Touch so the sweep drops the ones that are never replayed.
      try {
        await file.setLastModified(DateTime.now());
      } catch (_) {
        // EDGE: some platforms refuse to set the stamp.
      }
      return bytes;
    } catch (_) {
      return null;
    }
  }

  Future<void> write(String key, List<int> bytes) async {
    if (key.isEmpty || bytes.isEmpty) return;
    try {
      final dir = await _root();
      if (dir == null) return;
      final file = File('${dir.path}${Platform.pathSeparator}$key.mp3');
      await file.writeAsBytes(bytes, flush: false);
      await _sweep(dir);
    } catch (_) {
      // EDGE: no space or no permission — playback already has the bytes.
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
      for (final path in ttsCacheEvictions(files: files)) {
        try {
          await File(path).delete();
        } catch (_) {
          // EDGE: already gone.
        }
      }
    } catch (_) {
      // EDGE: listing failed — leave the folder alone.
    }
  }
}
