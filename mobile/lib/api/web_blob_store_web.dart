/// design/462 — paper bytes kept in the browser (IndexedDB) for the upload queue.
/// The web has no app documents folder, so the queue's file copy lives here.
library;

import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

const _dbName = 'asr_blobs';
const _storeName = 'files';

Future<web.IDBDatabase> _open() {
  final done = Completer<web.IDBDatabase>();
  final req = web.window.indexedDB.open(_dbName, 1);
  req.onupgradeneeded = ((web.Event _) {
    final db = req.result as web.IDBDatabase;
    if (!db.objectStoreNames.contains(_storeName)) db.createObjectStore(_storeName);
  }).toJS;
  req.onsuccess = ((web.Event _) => done.complete(req.result as web.IDBDatabase)).toJS;
  req.onerror = ((web.Event _) => done.completeError(StateError('idb_open'))).toJS;
  return done.future;
}

Future<JSAny?> _await(web.IDBRequest req) {
  final done = Completer<JSAny?>();
  req.onsuccess = ((web.Event _) => done.complete(req.result)).toJS;
  req.onerror = ((web.Event _) => done.completeError(StateError('idb_request'))).toJS;
  return done.future;
}

web.IDBObjectStore _store(web.IDBDatabase db, String mode) =>
    db.transaction(_storeName.toJS, mode).objectStore(_storeName);

Future<bool> webBlobPut(String key, List<int> bytes) async {
  try {
    final db = await _open();
    final data = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
    await _await(_store(db, 'readwrite').put(data.toJS, key.toJS));
    return true;
  } catch (_) {
    return false;
  }
}

Future<Uint8List?> webBlobGet(String key) async {
  try {
    final db = await _open();
    final v = await _await(_store(db, 'readonly').get(key.toJS));
    if (v == null) return null;
    return (v as JSUint8Array).toDart;
  } catch (_) {
    return null;
  }
}

Future<void> webBlobDelete(String key) async {
  try {
    final db = await _open();
    await _await(_store(db, 'readwrite').delete(key.toJS));
  } catch (_) {}
}
