import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
import 'package:sentence_reading/widgets/sentence_equations.dart';

const _png = 'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg==';

Map<String, dynamic> _eq(String id, {double w = 190, double h = 19}) =>
    {'id': id, 'src': _png, 'w': w, 'h': h};

void main() {
  test('design/481: equation rows are read, bad ones dropped', () {
    final s = SentenceView.fromJson({
      'id': 's0',
      'text': 'The energy is given by',
      'equations': [
        _eq('eq_001'),
        {'id': 'x', 'src': 'https://x/y.png', 'w': 10, 'h': 10},
        {'id': 'y', 'src': _png, 'w': 0, 'h': 10},
        'nope',
      ],
    });
    expect(s.equations.map((e) => e.id), ['eq_001']);
    expect(s.equations.single.w, 190);
    expect(s.withHeading('2. Theory').equations.single.id, 'eq_001');
    expect(SentenceView.fromJson({'id': 's1', 'text': 'Plain.'}).equations, isEmpty);
  });

  test('design/481: the on-device copy keeps the equations', () {
    final session = ReadingSession.fromOpenJson({
      'title': 'A paper title',
      'sentences': [
        {'id': 's0', 'text': 'The energy is given by', 'section': 'body', 'equations': [_eq('eq_001')]},
        {'id': 's1', 'text': 'where m is the mass.', 'section': 'body'},
      ],
    });
    final disk = readingSessionToPaperDiskJson(session);
    final rows = disk['sentences'] as List;
    expect((rows[1] as Map).containsKey('equations'), isFalse);
    final back = ReadingSession.fromOpenJson(disk);
    expect(back.sentences.first.equations.single.src, _png);
    expect(back.sentences.first.equations.single.h, 19);
  });

  test('design/481: the tint sends white to the page and black to the ink', () {
    List<double> apply(ColorFilter f, double v) {
      final m = _matrixOf(f);
      return [
        for (var r = 0; r < 3; r++) m[r * 5] * v * 255 + m[r * 5 + 4],
      ];
    }

    const ink = Color(0xFF202020);
    const paper = Color(0xFFF4ECD8);
    final f = equationTint(ink: ink, paper: paper);
    final white = apply(f, 1);
    final black = apply(f, 0);
    expect(white[0], closeTo(0xF4, 0.6));
    expect(white[1], closeTo(0xEC, 0.6));
    expect(white[2], closeTo(0xD8, 0.6));
    expect(black, everyElement(closeTo(0x20, 0.6)));
  });

  testWidgets('design/481: a picture reads at the sentence size and fits the column',
      (tester) async {
    Future<Size> shown(double width, double w) async {
      await tester.pumpWidget(MaterialApp(
        home: Align(
          alignment: Alignment.topLeft,
          child: SizedBox(
            width: width,
            child: SentenceEquations(
              equations: [EquationView.fromJson(_eq('eq_001', w: w, h: w / 10))!],
              style: const TextStyle(fontSize: 19),
            ),
          ),
        ),
      ));
      return tester.getSize(find.byType(Image));
    }

    final narrow = await shown(1000, 95);
    expect(narrow.width, closeTo(95 * 19 / kEquationPagePt, 0.01));
    expect(narrow.height, closeTo(narrow.width / 10, 0.01));
    final wide = await shown(300, 400);
    expect(wide.width, closeTo(300, 0.01));
    expect(wide.height, closeTo(30, 0.01));
    expect(find.bySemanticsLabel(RegExp('.')), findsNothing);
  });
}

List<double> _matrixOf(ColorFilter f) {
  final text = f.toString();
  final inner = text.substring(text.indexOf('[') + 1, text.lastIndexOf(']'));
  return [for (final p in inner.split(',')) double.parse(p.trim())];
}
