import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reading_models.dart';

String _png(int n) => 'data:image/png;base64,${base64Encode(List<int>.filled(16, n))}';

void main() {
  test('design/426: the same figure gives the same bytes on every rebuild', () {
    final a = _png(1);
    final first = decodeRasterDataUrlCached(a)!;
    final again = decodeRasterDataUrlCached(String.fromCharCodes(a.codeUnits))!;
    expect(identical(first.bytes, again.bytes), isTrue,
        reason: 'an equal string read again from disk is still the same figure');
    expect(identical(decodeRasterDataUrl(a)!.bytes, first.bytes), isFalse,
        reason: 'the plain decoder makes new bytes; that was the blink');

    final b = decodeRasterDataUrlCached(_png(2))!;
    expect(identical(b.bytes, first.bytes), isFalse);
    expect(decodeRasterDataUrlCached('not an image'), isNull);
    expect(decodeRasterDataUrlCached(null), isNull);
  });

  test('design/426: only the last few figures are kept', () {
    final keep = decodeRasterDataUrlCached(_png(100))!;
    for (var i = 0; i < kFigureBytesCacheSize; i++) {
      decodeRasterDataUrlCached(_png(101 + i));
    }
    expect(identical(decodeRasterDataUrlCached(_png(100))!.bytes, keep.bytes), isFalse,
        reason: 'pushed out after $kFigureBytesCacheSize newer figures');
  });
}
