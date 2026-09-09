/// design/197 — native PDF page PNG for figure layout edit background.
library;

import "dart:typed_data";

import "package:flutter/foundation.dart";
import "package:flutter/services.dart";

const MethodChannel _kPdfPreviewChannel = MethodChannel("asr/pdf_page_preview");

class PdfPagePreview {
  /// Render [pageIndex] (0-based) from a local PDF [path]. Android only for now.
  static Future<Uint8List?> renderPagePng(
    String path, {
    required int pageIndex,
    int maxSidePx = 1400,
  }) async {
    final p = path.trim();
    if (p.isEmpty || pageIndex < 0) return null;
    if (!p.toLowerCase().endsWith(".pdf")) return null;
    if (kIsWeb) return null;
    try {
      final raw = await _kPdfPreviewChannel.invokeMethod<dynamic>(
        "renderPagePng",
        {
          "path": p,
          "pageIndex": pageIndex,
          "maxSidePx": maxSidePx,
        },
      );
      if (raw is Uint8List) return raw;
      if (raw is List<int>) return Uint8List.fromList(raw);
      return null;
    } catch (_) {
      return null;
    }
  }
}
