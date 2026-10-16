/// design/409 - paper files in the browser's IndexedDB, keyed by path.
library;

import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:web/web.dart' as web;

import 'disk_fs.dart';

const _dbName = 'asr_disk';
const _storeName = 'files';

IdbDiskFs? _instance;

DiskFs? openBrowserDisk() => _instance ??= IdbDiskFs();

/// Keys are only paths and values only bytes, because [write] stores nothing else.
///
/// Each write is one transaction whose requests are all queued before it is
/// awaited, so a transaction never waits on Dart code and cannot close half done.
class IdbDiskFs implements DiskFs {
  IdbDiskFs() {
    unawaited(_askToKeep());
  }

  Future<web.IDBDatabase>? _db;

  /// Without this the browser may clear the papers when its disk runs low.
  Future<void> _askToKeep() async {
    try {
      await web.window.navigator.storage.persist().toDart;
    } catch (_) {}
  }

  Future<web.IDBDatabase> _open() {
    return _db ??= () {
      final done = Completer<web.IDBDatabase>();
      final req = web.window.indexedDB.open(_dbName, 1);
      req.onupgradeneeded = ((web.Event _) {
        final db = req.result as web.IDBDatabase;
        if (!db.objectStoreNames.contains(_storeName)) {
          db.createObjectStore(_storeName);
        }
      }).toJS;
      req.onsuccess = ((web.Event _) {
        done.complete(req.result as web.IDBDatabase);
      }).toJS;
      req.onerror = ((web.Event _) {
        _db = null;
        done.completeError(DiskFsException('idb_open', '${req.error?.message}'));
      }).toJS;
      return done.future;
    }();
  }

  Future<web.IDBTransaction> _txn(String mode) async =>
      (await _open()).transaction(_storeName.toJS, mode);

  static Future<JSAny?> _result(web.IDBRequest req) {
    final done = Completer<JSAny?>();
    req.onsuccess = ((web.Event _) => done.complete(req.result)).toJS;
    req.onerror = ((web.Event _) {
      done.completeError(DiskFsException('idb', '${req.error?.message}'));
    }).toJS;
    return done.future;
  }

  static Future<void> _committed(web.IDBTransaction txn) {
    final done = Completer<void>();
    txn.oncomplete = ((web.Event _) => done.complete()).toJS;
    void fail(web.Event _) {
      if (!done.isCompleted) {
        done.completeError(DiskFsException('idb_txn', '${txn.error?.message}'));
      }
    }

    txn.onerror = fail.toJS;
    txn.onabort = fail.toJS;
    return done.future;
  }

  static String _n(String path) => p.url.normalize(path);

  static web.IDBKeyRange _below(String dir) {
    final base = _n(dir);
    final lo = base.endsWith('/') ? base : '$base/';
    return web.IDBKeyRange.bound(lo.toJS, '$lo\uffff'.toJS);
  }

  Future<List<String>> _keys(JSAny query, [int? count]) async {
    final store = (await _txn('readonly')).objectStore(_storeName);
    final req = count == null ? store.getAllKeys(query) : store.getAllKeys(query, count);
    final res = await _result(req);
    if (res == null) return const [];
    return [
      for (final k in (res as JSArray<JSAny?>).toDart)
        if (k != null) (k as JSString).toDart,
    ];
  }

  @override
  Future<bool> isFile(String path) async =>
      (await _keys(_n(path).toJS, 1)).isNotEmpty;

  @override
  Future<bool> isDir(String path) async =>
      (await _keys(_below(path), 1)).isNotEmpty;

  @override
  Future<Uint8List?> read(String path) async {
    final store = (await _txn('readonly')).objectStore(_storeName);
    final res = await _result(store.get(_n(path).toJS));
    if (res == null) return null;
    return (res as JSUint8Array).toDart;
  }

  @override
  Future<void> write(String path, List<int> bytes) async {
    final data = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
    final txn = await _txn('readwrite');
    txn.objectStore(_storeName).put(data.toJS, _n(path).toJS);
    await _committed(txn);
  }

  @override
  Future<void> rename(String from, String to) async {
    final bytes = await read(from);
    if (bytes == null) throw DiskFsException('missing', from);
    final txn = await _txn('readwrite');
    final store = txn.objectStore(_storeName);
    store.put(bytes.toJS, _n(to).toJS);
    store.delete(_n(from).toJS);
    await _committed(txn);
  }

  @override
  Future<void> deleteFile(String path) async {
    if (!await isFile(path)) throw DiskFsException('missing', path);
    final txn = await _txn('readwrite');
    txn.objectStore(_storeName).delete(_n(path).toJS);
    await _committed(txn);
  }

  @override
  Future<void> deleteTree(String path) async {
    final txn = await _txn('readwrite');
    txn.objectStore(_storeName).delete(_below(path));
    await _committed(txn);
  }

  @override
  Future<void> makeDir(String path) async {}

  @override
  Future<List<DiskChild>> children(String dir) async =>
      childrenAmong(await _keys(_below(dir)), dir, p.url);
}
