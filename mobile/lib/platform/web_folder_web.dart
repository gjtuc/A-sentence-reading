/// design/416 - 논문 폴더 연결 on the web: Chrome's folder access (File System Access).
///
/// A connected folder is kept as a handle in IndexedDB under a key, and the app sees
/// it as `webdir:<key>`; a file inside is `webdir:<key>/<path>`. The browser may ask
/// again for permission after a reload; that needs a click, so a list without
/// permission reports `stale` and 「다시 연결」 asks on the click.
library;

import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:flutter/services.dart';
import 'package:web/web.dart' as web;

import 'saf_tree_channel.dart';
import 'web_folder_paths.dart';

const _dbName = 'asr_folders';
const _storeName = 'handles';

/// Folders below this depth are not walked.
const int _maxDepth = 6;

@JS('showDirectoryPicker')
external JSPromise<JSObject> _showDirectoryPicker(JSObject options);

extension type _Handle(JSObject _) implements JSObject {
  external String get kind;
  external String get name;
}

extension type _Dir(JSObject _) implements _Handle {
  external JSObject values();
  external JSPromise<JSObject> getDirectoryHandle(String name);
  external JSPromise<JSObject> getFileHandle(String name);
  external JSPromise<JSString> queryPermission(JSObject options);
  external JSPromise<JSString> requestPermission(JSObject options);
}

extension type _FileHandle(JSObject _) implements _Handle {
  external JSPromise<web.File> getFile();
}

extension type _Iter(JSObject _) implements JSObject {
  external JSPromise<_Step> next();
}

extension type _Step(JSObject _) implements JSObject {
  external bool get done;
  external JSObject? get value;
}

final Map<String, _Dir> _roots = {};
final Map<String, _FileHandle> _files = {};

bool get webFolderSupported => globalContext.has('showDirectoryPicker');

JSObject _readMode() => {'mode': 'read'}.jsify()! as JSObject;

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

Future<void> _put(String key, JSObject handle) async {
  final db = await _open();
  final store = db.transaction(_storeName.toJS, 'readwrite').objectStore(_storeName);
  await _await(store.put(handle, key.toJS));
}

Future<_Dir?> _get(String key) async {
  final db = await _open();
  final store = db.transaction(_storeName.toJS, 'readonly').objectStore(_storeName);
  final v = await _await(store.get(key.toJS));
  return v == null ? null : _Dir(v as JSObject);
}

Future<void> _delete(String key) async {
  final db = await _open();
  final store = db.transaction(_storeName.toJS, 'readwrite').objectStore(_storeName);
  await _await(store.delete(key.toJS));
}

Future<_Dir?> _root(String key) async {
  final hit = _roots[key];
  if (hit != null) return hit;
  final dir = await _get(key);
  if (dir != null) _roots[key] = dir;
  return dir;
}

Future<bool> _granted(_Dir dir, {required bool ask}) async {
  try {
    final now = (await dir.queryPermission(_readMode()).toDart).toDart;
    if (now == 'granted') return true;
    if (!ask) return false;
    return (await dir.requestPermission(_readMode()).toDart).toDart == 'granted';
  } catch (_) {
    return false;
  }
}

PlatformException _stale() => PlatformException(code: 'stale');

/// On 「다시 연결」 the folder connected before is asked for again first; the
/// picker opens only when that is refused or there was none.
Future<SafTreePickResult?> webPickFolder({String? previous, bool downloads = false}) async {
  final prevKey = webFolderKey(previous ?? '');
  if (prevKey != null) {
    final dir = await _root(prevKey);
    if (dir != null && await _granted(dir, ask: true)) {
      return SafTreePickResult(treeUri: previous!.trim(), displayLabel: dir.name);
    }
  }
  if (!webFolderSupported) return null;
  final JSObject picked;
  try {
    picked = await _showDirectoryPicker({
      'id': downloads ? 'asr_downloads' : 'asr_papers',
      'mode': 'read',
      if (downloads) 'startIn': 'downloads',
    }.jsify()! as JSObject)
        .toDart;
  } catch (_) {
    return null;
  }
  final dir = _Dir(picked);
  final key = 'd${DateTime.now().millisecondsSinceEpoch}';
  _roots[key] = dir;
  try {
    await _put(key, dir);
  } catch (_) {}
  return SafTreePickResult(treeUri: webFolderTreeUri(key), displayLabel: dir.name);
}

Future<SafTreeListResult> webListPdfs(String treeUri, {int maxItems = 500}) async {
  final key = webFolderKey(treeUri);
  if (key == null) return const SafTreeListResult(items: [], truncated: false);
  final dir = await _root(key);
  if (dir == null || !await _granted(dir, ask: false)) throw _stale();
  final out = <SafTreePdfItem>[];
  var truncated = false;

  Future<void> walk(_Dir at, String prefix, int depth) async {
    final it = _Iter(at.values());
    while (true) {
      final step = await it.next().toDart;
      if (step.done) return;
      final raw = step.value;
      if (raw == null) continue;
      final h = _Handle(raw);
      final name = h.name;
      if (name.startsWith('.')) continue;
      if (h.kind == 'directory') {
        if (depth < _maxDepth) await walk(_Dir(raw), '$prefix$name/', depth + 1);
      } else if (webFolderListable(name)) {
        if (out.length >= maxItems) {
          truncated = true;
          return;
        }
        final fh = _FileHandle(raw);
        final file = await fh.getFile().toDart;
        final uri = webFolderDocUri(key, '$prefix$name');
        _files[uri] = fh;
        out.add(SafTreePdfItem(
          docUri: uri,
          displayName: name,
          sizeBytes: file.size,
          lastModifiedMs: file.lastModified,
        ));
      }
      if (truncated) return;
    }
  }

  try {
    await walk(dir, '', 0);
  } catch (_) {
    throw _stale();
  }
  return SafTreeListResult(items: out, truncated: truncated);
}

Future<_FileHandle?> _file(String docUri) async {
  final hit = _files[docUri];
  if (hit != null) return hit;
  final parts = webFolderDocParts(docUri);
  if (parts == null) return null;
  final dir = await _root(parts.key);
  if (dir == null || !await _granted(dir, ask: false)) throw _stale();
  var at = dir;
  final segs = parts.path.split('/');
  for (final s in segs.take(segs.length - 1)) {
    at = _Dir(await at.getDirectoryHandle(s).toDart);
  }
  final fh = _FileHandle(await at.getFileHandle(segs.last).toDart);
  _files[docUri] = fh;
  return fh;
}

Future<Uint8List?> webReadFile(String docUri, {int maxBytes = 50 * 1024 * 1024}) async {
  final fh = await _file(docUri);
  if (fh == null) return null;
  final file = await fh.getFile().toDart;
  if (file.size > maxBytes) throw PlatformException(code: 'too_large');
  final buf = await file.arrayBuffer().toDart;
  return buf.toDart.asUint8List();
}

/// SubtleCrypto is native; a Dart SHA-256 over a 10 MB PDF is slow in the browser.
Future<String?> webSha256(String docUri) async {
  try {
    final fh = await _file(docUri);
    if (fh == null) return null;
    final file = await fh.getFile().toDart;
    final buf = await file.arrayBuffer().toDart;
    final digest = await web.window.crypto.subtle.digest('SHA-256'.toJS, buf).toDart;
    final bytes = (digest as JSArrayBuffer).toDart.asUint8List();
    final sb = StringBuffer();
    for (final b in bytes) {
      sb.write(b.toRadixString(16).padLeft(2, '0'));
    }
    return sb.toString();
  } catch (_) {
    return null;
  }
}

Future<bool> webForgetFolder(String treeUri) async {
  final key = webFolderKey(treeUri);
  if (key == null) return false;
  _roots.remove(key);
  _files.removeWhere((k, _) => k.startsWith('${webFolderTreeUri(key)}/'));
  try {
    await _delete(key);
  } catch (_) {}
  return true;
}
