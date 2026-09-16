import 'dart:io';

import 'package:path/path.dart' as p;

import 'figure_disk_cache.dart';

/// design/307 — ids to keep (library + soft-hidden), compared as raw and token.
Set<String> residueKeepTokens(Iterable<String> ids) {
  final out = <String>{};
  for (final raw in ids) {
    final id = raw.trim();
    if (id.isEmpty) continue;
    out.add(id);
    final tok = figureCacheSafeToken(id, maxLen: 32);
    if (tok.isNotEmpty) out.add(tok);
  }
  return out;
}

/// Folder names present on disk but not in [keep].
Set<String> residueIdsNotInKeep({
  required Set<String> keep,
  required Iterable<String> found,
}) {
  final out = <String>{};
  for (final raw in found) {
    final id = raw.trim();
    if (id.isEmpty || keep.contains(id)) continue;
    out.add(id);
  }
  return out;
}

Future<List<String>> childDirNames(Directory? root) async {
  if (root == null || !await root.exists()) return const [];
  final out = <String>[];
  await for (final e in root.list(followLinks: false)) {
    if (e is Directory) out.add(p.basename(e.path));
  }
  return out;
}

Future<int> deleteNamedChildDirs(Directory? root, Set<String> names) async {
  if (root == null || names.isEmpty || !await root.exists()) return 0;
  var n = 0;
  for (final name in names) {
    final dir = Directory(p.join(root.path, name));
    if (!await dir.exists()) continue;
    try {
      await dir.delete(recursive: true);
      n += 1;
    } catch (_) {}
  }
  return n;
}
