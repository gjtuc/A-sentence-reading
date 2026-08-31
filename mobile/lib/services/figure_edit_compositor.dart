/// Local slot PNG compositor — union crop + body/caption vstack (design/163).
library;

import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'figure_edit_geometry.dart';

Uint8List? cropNormRect(Uint8List pagePng, NormRect rect) {
  if (!rect.isValid) return null;
  final decoded = img.decodeImage(pagePng);
  if (decoded == null) return null;
  final x = (rect.left * decoded.width).round().clamp(0, decoded.width - 1);
  final y = (rect.top * decoded.height).round().clamp(0, decoded.height - 1);
  final x2 = (rect.right * decoded.width).round().clamp(x + 1, decoded.width);
  final y2 =
      (rect.bottom * decoded.height).round().clamp(y + 1, decoded.height);
  final w = x2 - x;
  final h = y2 - y;
  if (w < 2 || h < 2) return null;
  final cropped = img.copyCrop(decoded, x: x, y: y, width: w, height: h);
  return Uint8List.fromList(img.encodePng(cropped));
}

Uint8List? vstackPngs(List<Uint8List> strips) {
  final images = <img.Image>[];
  for (final raw in strips) {
    final im = img.decodeImage(raw);
    if (im != null && im.width > 1 && im.height > 1) {
      images.add(im);
    }
  }
  if (images.isEmpty) return null;
  if (images.length == 1) {
    return Uint8List.fromList(img.encodePng(images.first));
  }
  final maxW = images.map((e) => e.width).reduce((a, b) => a > b ? a : b);
  var totalH = 0;
  for (final im in images) {
    totalH += im.height;
  }
  final canvas = img.Image(width: maxW, height: totalH);
  img.fill(canvas, color: img.ColorRgb8(255, 255, 255));
  var y = 0;
  for (final im in images) {
    final xOff = (maxW - im.width) ~/ 2;
    img.compositeImage(canvas, im, dstX: xOff, dstY: y);
    y += im.height;
  }
  return Uint8List.fromList(img.encodePng(canvas));
}

Uint8List? composeSlotPng({
  required Uint8List? bodyPagePng,
  required NormRect? bodyRect,
  required Uint8List? captionPagePng,
  required NormRect? captionRect,
  required bool isTable,
}) {
  final body = bodyPagePng != null && bodyRect != null
      ? cropNormRect(bodyPagePng, bodyRect)
      : null;
  final cap = captionPagePng != null && captionRect != null
      ? cropNormRect(captionPagePng, captionRect)
      : null;
  final strips = <Uint8List>[];
  if (isTable) {
    if (cap != null) strips.add(cap);
    if (body != null) strips.add(body);
  } else {
    if (body != null) strips.add(body);
    if (cap != null) strips.add(cap);
  }
  if (strips.isEmpty) return null;
  return vstackPngs(strips);
}
