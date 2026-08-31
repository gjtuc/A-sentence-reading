import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/annotation_models.dart';

void main() {
  group('AnnotationEvent', () {
    test('round-trip JSON', () {
      final ev = annotationEventNow(
        id: 'a1',
        color: 'green',
        note: 'memo',
        sentenceId: 's1',
      );
      final parsed = AnnotationEvent.fromJson(ev.toJson());
      expect(parsed, isNotNull);
      expect(parsed!.id, 'a1');
      expect(parsed.color, 'green');
      expect(parsed.note, 'memo');
      expect(parsed.sentenceId, 's1');
    });
  });

  group('mergeAnnotationsStores', () {
    test('latest at wins per id', () {
      final a = AnnotationsStore(papers: {
        'cache:p1': PaperAnnotations(sentences: {
          'intro:1': [
            annotationEventNow(id: 'x', color: 'yellow', sentenceId: 's1'),
          ],
        }),
      });
      final b = AnnotationsStore(papers: {
        'cache:p1': PaperAnnotations(sentences: {
          'intro:1': [
            annotationEventNow(id: 'x', deleted: true, sentenceId: 's1'),
          ],
        }),
      });
      final merged = mergeAnnotationsStores(a, b);
      expect(merged.papers['cache:p1']?.sentences['intro:1'], isNull);
    });
  });
}
