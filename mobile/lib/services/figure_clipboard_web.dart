/// design/434 - the browser's clipboard takes pictures as PNG only, so a JPEG
/// figure is redrawn as PNG first.
library;

import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

Future<bool> copy(Uint8List bytes, String mime, String question, Duration gap) async {
  try {
    final clip = web.window.navigator.clipboard;
    if (question.isNotEmpty) {
      await clip.writeText(question).toDart;
      await Future<void>.delayed(gap);
    }
    final png = await _png(bytes, mime);
    final data = JSObject()..setProperty('image/png'.toJS, png);
    await clip.write(<web.ClipboardItem>[web.ClipboardItem(data)].toJS).toDart;
    return true;
  } catch (_) {
    return false;
  }
}

Future<web.Blob> _png(Uint8List bytes, String mime) async {
  final src = web.Blob(
    <JSAny>[bytes.toJS].toJS,
    web.BlobPropertyBag(type: mime.isEmpty ? 'image/png' : mime),
  );
  if (mime == 'image/png') return src;
  final bitmap = await web.window.createImageBitmap(src).toDart;
  final canvas = web.OffscreenCanvas(bitmap.width, bitmap.height);
  final ctx = canvas.getContext('2d')! as web.OffscreenCanvasRenderingContext2D;
  ctx.fillStyle = 'white'.toJS;
  ctx.fillRect(0, 0, bitmap.width, bitmap.height);
  ctx.drawImage(bitmap, 0, 0);
  return canvas.convertToBlob(web.ImageEncodeOptions(type: 'image/png')).toDart;
}
