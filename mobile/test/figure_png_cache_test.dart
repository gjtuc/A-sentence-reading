import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/figure_png_cache.dart';

void main() {
  test('paper and figure make one file name', () {
    final a = figurePngName(cacheId: 'abc123', figureId: 'fig-2');
    expect(a, 'abc123.fig-2.png');
    expect(figurePngName(cacheId: ' abc123 ', figureId: 'fig-2'), a);
    expect(
      figurePngName(cacheId: 'abc123', figureId: 'fig-3'),
      isNot(a),
    );
  });

  test('a path character cannot escape the folder', () {
    final name = figurePngName(cacheId: '../../etc', figureId: 'a/b');
    expect(name.contains('/'), isFalse);
    expect(name.contains('..'), isFalse);
  });

  test('an empty id makes no file name', () {
    expect(figurePngName(cacheId: '', figureId: 'fig-1'), '');
    expect(figurePngName(cacheId: 'abc', figureId: '   '), '');
  });
}
