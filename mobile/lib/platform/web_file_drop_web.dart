/// design/458 — PDFs dragged from the file explorer and dropped on the web app.
///
/// The browser would open a dropped PDF in the tab, so the window's drag events
/// are taken in the capture phase before Flutter's view sees them.
library;

import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import '../api/upload_limits.dart';
import 'file_drop_rules.dart';

typedef DroppedFile = ({String name, Uint8List bytes});

bool _carriesFiles(web.DragEvent e) {
  final types = e.dataTransfer?.types.toDart ?? const <JSString>[];
  return types.any((t) => t.toDart == 'Files');
}

/// [onOver] says whether files are held over the window; [onFiles] gets the
/// dropped PDF and Word files and how many other files were left out. Returns the remover.
void Function() installFileDrop({
  required void Function(bool over) onOver,
  required void Function(List<DroppedFile> files, int skipped) onFiles,
  int maxBytes = kMaxUploadBytes,
}) {
  var depth = 0;
  void enter(web.Event raw) {
    final e = raw as web.DragEvent;
    if (!_carriesFiles(e)) return;
    e.preventDefault();
    depth += 1;
    if (depth == 1) onOver(true);
  }

  void leave(web.Event raw) {
    final e = raw as web.DragEvent;
    if (!_carriesFiles(e)) return;
    depth = depth > 0 ? depth - 1 : 0;
    if (depth == 0) onOver(false);
  }

  void over(web.Event raw) {
    final e = raw as web.DragEvent;
    if (!_carriesFiles(e)) return;
    e.preventDefault();
    e.dataTransfer?.dropEffect = 'copy';
  }

  void drop(web.Event raw) {
    final e = raw as web.DragEvent;
    if (!_carriesFiles(e)) return;
    e.preventDefault();
    e.stopPropagation();
    depth = 0;
    onOver(false);
    final list = e.dataTransfer?.files;
    if (list == null) return;
    final files = <web.File>[for (var i = 0; i < list.length; i++) list.item(i)!];
    unawaited(() async {
      final out = <DroppedFile>[];
      var skipped = 0;
      for (final f in files) {
        if (!droppableDoc(f.name, f.size, maxBytes: maxBytes)) {
          skipped += 1;
          continue;
        }
        try {
          final buf = await f.arrayBuffer().toDart;
          out.add((name: f.name, bytes: buf.toDart.asUint8List()));
        } catch (_) {
          skipped += 1;
        }
      }
      onFiles(out, skipped);
    }());
  }

  final handlers = <String, JSFunction>{
    'dragenter': enter.toJS,
    'dragleave': leave.toJS,
    'dragover': over.toJS,
    'drop': drop.toJS,
  };
  for (final h in handlers.entries) {
    web.window.addEventListener(h.key, h.value, true.toJS);
  }
  return () {
    for (final h in handlers.entries) {
      web.window.removeEventListener(h.key, h.value, true.toJS);
    }
  };
}
