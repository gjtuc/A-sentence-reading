/// design/410 — near sync reads and writes the device's own paper store.
library;

import 'dart:typed_data';

import '../api/progress_store.dart';
import '../practice_sample/sample_seed.dart';
import 'near_sync.dart';
import 'paper_disk_store.dart';
import 'shadowing_disk_store.dart';

class LibraryNearLocal implements NearLocal, NearForget {
  LibraryNearLocal({
    required this.disk,
    required this.uid,
    this.shadow,
    this.loadGone,
    this.hiddenIds,
    this.onForget,
  });

  final PaperDiskStore disk;
  final String? uid;

  /// Shadowing takes, chunk plans and voice files (design/187).
  final ShadowingDiskStore? shadow;

  /// design/450 — the library's delete record, hidden set and delete step.
  final Future<Map<String, int>> Function()? loadGone;
  final Set<String> Function()? hiddenIds;
  final Future<void> Function(Map<String, int> gone, List<String> drop)?
      onForget;

  @override
  Future<List<NearPaper>> papers() async {
    final out = <NearPaper>[];
    for (final e in await disk.listIndex()) {
      if (e.id.isEmpty || isSampleCacheId(e.id)) continue;
      if (!await disk.hasSession(e.id)) continue;
      out.add(NearPaper(
        id: e.id,
        title: e.title,
        hash: e.contentHash,
        added: e.addedMs,
      ));
    }
    return out;
  }

  @override
  Future<Map<String, int>> gone() async =>
      await loadGone?.call() ?? const <String, int>{};

  @override
  Future<Set<String>> hidden() async => hiddenIds?.call() ?? const <String>{};

  @override
  Future<void> forget(Map<String, int> gone, List<String> drop) async {
    await onForget?.call(gone, drop);
  }

  @override
  Future<Map<String, Uint8List>> pack(String id) =>
      disk.collectTransferPackFiles(id);

  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) =>
      disk.replaceFromTransferPack(
        cacheId: paper.id,
        title: paper.title,
        files: files,
        contentHash: paper.hash,
      );

  @override
  Future<Map<String, Map<String, dynamic>>> progress() =>
      loadProgressRows(uid: uid);

  @override
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> rows) =>
      mergeProgressRows(uid: uid, incoming: rows);

  @override
  Future<Map<String, List<String>>> extraNames() async {
    final s = shadow;
    if (s == null) return const {};
    final out = <String, List<String>>{};
    for (final id in await s.listChildDirNames()) {
      final names = await s.listVoiceNames(id);
      if (names.isNotEmpty) out[id] = names;
    }
    return out;
  }

  @override
  Future<Map<String, Uint8List>> extraPack(
    String id,
    Set<String> skipNames,
  ) async {
    final s = shadow;
    if (s == null) return const {};
    final files = await s.listPackFiles(id);
    files.removeWhere(
      (rel, _) =>
          rel.startsWith('shadowing/voice/') &&
          skipNames.contains(rel.substring('shadowing/voice/'.length)),
    );
    return files;
  }

  @override
  Future<int> mergeExtra(String id, Map<String, Uint8List> files) async {
    final s = shadow;
    if (s == null) return 0;
    return s.mergePackFiles(id, files);
  }
}
