/// design/409 - the few file operations the paper store needs, over the app
/// folder (dart:io) on a phone and browser storage (IndexedDB) on the web.
///
/// Folders in browser storage are implied by the files under them: a folder
/// exists once a file is written below it, and creating one stores nothing.
/// [MemoryDiskFs] follows the same rule so a VM test sees what the web sees.
library;

import 'dart:convert';
import 'dart:io' as io;

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import 'browser_disk_stub.dart'
    if (dart.library.js_interop) 'browser_disk_web.dart';
import 'local_disk.dart';

class DiskFsException implements Exception {
  DiskFsException(this.code, this.path);

  final String code;
  final String path;

  @override
  String toString() => 'DiskFsException($code): $path';
}

typedef DiskChild = ({String path, bool dir});

abstract class DiskFs {
  Future<bool> isFile(String path);
  Future<bool> isDir(String path);

  /// Null when there is no file at [path].
  Future<Uint8List?> read(String path);
  Future<void> write(String path, List<int> bytes);
  Future<void> rename(String from, String to);
  Future<void> deleteFile(String path);
  Future<void> deleteTree(String path);
  Future<void> makeDir(String path);
  Future<List<DiskChild>> children(String dir);
}

/// Lets a VM test stand in for browser storage.
@visibleForTesting
DiskFs? debugBrowserDisk;

DiskFs? get _browserDisk => debugBrowserDisk ?? openBrowserDisk();

/// True on the web when the browser gives us storage.
bool get browserDiskAvailable => !localDiskAvailable && _browserDisk != null;

DiskFs get diskFs {
  if (localDiskAvailable) return const IoDiskFs();
  final web = _browserDisk;
  if (web == null) throw DiskFsException('no_disk', '');
  return web;
}

abstract class DiskEntity {
  const DiskEntity(this.path);

  final String path;
}

class DiskFile extends DiskEntity {
  const DiskFile(super.path);

  DiskDir get parent => DiskDir(p.dirname(path));

  Future<bool> exists() => diskFs.isFile(path);

  Future<Uint8List> readAsBytes() async {
    final bytes = await diskFs.read(path);
    if (bytes == null) throw DiskFsException('missing', path);
    return bytes;
  }

  Future<String> readAsString() async => utf8.decode(await readAsBytes());

  Future<DiskFile> writeAsBytes(List<int> bytes, {bool flush = false}) async {
    await diskFs.write(path, bytes);
    return this;
  }

  Future<DiskFile> rename(String newPath) async {
    await diskFs.rename(path, newPath);
    return DiskFile(newPath);
  }

  Future<void> delete() => diskFs.deleteFile(path);
}

class DiskDir extends DiskEntity {
  const DiskDir(super.path);

  Future<bool> exists() => diskFs.isDir(path);

  Future<DiskDir> create({bool recursive = false}) async {
    await diskFs.makeDir(path);
    return this;
  }

  /// Always recursive, which is the only way the paper store deletes.
  Future<void> delete({bool recursive = true}) => diskFs.deleteTree(path);

  Stream<DiskEntity> list({bool followLinks = false}) async* {
    for (final c in await diskFs.children(path)) {
      yield c.dir ? DiskDir(c.path) : DiskFile(c.path);
    }
  }
}

class IoDiskFs implements DiskFs {
  const IoDiskFs();

  @override
  Future<bool> isFile(String path) => io.File(path).exists();

  @override
  Future<bool> isDir(String path) => io.Directory(path).exists();

  @override
  Future<Uint8List?> read(String path) async {
    final f = io.File(path);
    if (!await f.exists()) return null;
    return f.readAsBytes();
  }

  @override
  Future<void> write(String path, List<int> bytes) async {
    await io.File(path).writeAsBytes(bytes, flush: true);
  }

  @override
  Future<void> rename(String from, String to) async {
    await io.File(from).rename(to);
  }

  @override
  Future<void> deleteFile(String path) async {
    await io.File(path).delete();
  }

  @override
  Future<void> deleteTree(String path) async {
    await io.Directory(path).delete(recursive: true);
  }

  @override
  Future<void> makeDir(String path) async {
    await io.Directory(path).create(recursive: true);
  }

  @override
  Future<List<DiskChild>> children(String dir) async {
    return [
      await for (final e in io.Directory(dir).list(followLinks: false))
        (path: e.path, dir: e is io.Directory),
    ];
  }
}

/// Children of [dir] among [keys], which are file paths. Shared by the memory
/// and browser stores, whose folders exist only through the files below them.
List<DiskChild> childrenAmong(Iterable<String> keys, String dir, p.Context ctx) {
  final base = ctx.normalize(dir);
  final seen = <String, bool>{};
  for (final k in keys) {
    if (!ctx.isWithin(base, k)) continue;
    final parts = ctx.split(ctx.relative(k, from: base));
    if (parts.isEmpty) continue;
    final child = ctx.join(base, parts.first);
    final isDir = parts.length > 1;
    seen[child] = (seen[child] ?? false) || isDir;
  }
  return [for (final e in seen.entries) (path: e.key, dir: e.value)];
}

/// In-memory files, with the browser's folder rule.
class MemoryDiskFs implements DiskFs {
  final Map<String, Uint8List> files = {};

  String _n(String path) => p.normalize(path);

  @override
  Future<bool> isFile(String path) async => files.containsKey(_n(path));

  @override
  Future<bool> isDir(String path) async {
    final d = _n(path);
    return files.keys.any((k) => p.isWithin(d, k));
  }

  @override
  Future<Uint8List?> read(String path) async => files[_n(path)];

  @override
  Future<void> write(String path, List<int> bytes) async {
    files[_n(path)] = Uint8List.fromList(bytes);
  }

  @override
  Future<void> rename(String from, String to) async {
    final bytes = files.remove(_n(from));
    if (bytes == null) throw DiskFsException('missing', from);
    files[_n(to)] = bytes;
  }

  @override
  Future<void> deleteFile(String path) async {
    if (files.remove(_n(path)) == null) throw DiskFsException('missing', path);
  }

  @override
  Future<void> deleteTree(String path) async {
    final d = _n(path);
    files.removeWhere((k, _) => p.isWithin(d, k));
  }

  @override
  Future<void> makeDir(String path) async {}

  @override
  Future<List<DiskChild>> children(String dir) async =>
      childrenAmong(files.keys, dir, p.context);
}
