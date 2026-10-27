import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reader_nav_labels.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';

List<SentenceView> _paper() => [
      SentenceView(id: 't', text: 'T', section: 'title'),
      SentenceView(id: 'a1', text: 'a1', section: 'body'),
      SentenceView(id: 'a2', text: 'a2', section: 'body'),
      SentenceView(id: 'i1', text: 'i1', section: 'introduction'),
      SentenceView(id: 'b1', text: 'b1', section: 'body'),
      SentenceView(id: 'b2', text: 'b2', section: 'body'),
      SentenceView(id: 'b3', text: 'b3', section: 'body'),
      SentenceView(id: 's1', text: 's1', section: 'supplementary'),
    ];

const _heads = [
  {'text': 'CONSPECTUS', 'from': 'a1'},
  {'text': '1. INTRODUCTION', 'from': 'i1'},
  {'text': '2. Multiple Interactions', 'from': 'b1'},
  {'text': '2. Multiple Interactions \u203a 2.1. Metal-Metal', 'from': 'b2'},
  {'text': '', 'from': 's1'},
];

void main() {
  test('design/469: headings carry from their start to the next one', () {
    final s = applyPaperHeadings(_paper(), _heads);
    expect(s.map((e) => e.heading).toList(), [
      '',
      'CONSPECTUS',
      'CONSPECTUS',
      '1. INTRODUCTION',
      '2. Multiple Interactions',
      '2. Multiple Interactions \u203a 2.1. Metal-Metal',
      '2. Multiple Interactions \u203a 2.1. Metal-Metal',
      '',
    ]);
    expect(applyPaperHeadings(_paper(), null).every((e) => e.heading.isEmpty), isTrue);
  });

  test('design/469: picker groups follow reading order, labelled by heading', () {
    final nav = SectionNavIndex.fromSentences(applyPaperHeadings(_paper(), _heads));
    final labels = [for (var i = 0; i < nav.sectionCount; i++) nav.sectionLabelAt(i)];
    expect(labels, [
      'Title',
      'CONSPECTUS',
      '1. INTRODUCTION',
      '2. Multiple Interactions',
      '2.1. Metal-Metal',
      'Supplementary',
    ]);
    expect(nav.positionCountForSection(4), 2);
    expect(nav.globalIndexFor(4, 1), 6);
    expect(nav.selectionForGlobal(6), (4, 1));
    expect(nav.headerPartsFor(5).sectionName, '2.1. Metal-Metal');
    expect(nav.headerPartsFor(5).rightLabel, '1 / 2');
  });

  test('design/469: old papers without headings split into reading-order runs', () {
    final nav = SectionNavIndex.fromSentences(_paper());
    final labels = [for (var i = 0; i < nav.sectionCount; i++) nav.sectionLabelAt(i)];
    expect(labels, ['Title', 'Body', 'Introduction', 'Body', 'Supplementary']);
    expect(nav.positionCountForSection(1), 2);
    expect(nav.positionCountForSection(3), 3);
  });

  test('design/469: bookmark keys keep the whole-section numbering', () {
    final nav = SectionNavIndex.fromSentences(applyPaperHeadings(_paper(), _heads));
    expect(nav.sentenceBookmarkKeyForGlobal(1), 'body:1');
    expect(nav.sentenceBookmarkKeyForGlobal(4), 'body:3');
    expect(nav.sentenceBookmarkKeyForGlobal(6), 'body:5');
    expect(nav.sentenceBookmarkKeyForSelection(4, 1), 'body:5');
    expect(nav.globalIndexForBookmarkKey('body:3'), 4);
    expect(nav.isValidSentenceBookmarkKey('body:5'), isTrue);
    expect(nav.isValidSentenceBookmarkKey('body:6'), isFalse);
    final keys = {'body:1', 'body:4', 'body:5', 'introduction:1'};
    expect(nav.sectionBookmarkCount(keys, 1), 1);
    expect(nav.sectionBookmarkCount(keys, 2), 1);
    expect(nav.sectionBookmarkCount(keys, 4), 2);
  });

  test('design/469: the divider shows the heading where it changes', () {
    final s = applyPaperHeadings(_paper(), _heads);
    expect(
      [for (var i = 0; i < s.length; i++) sectionStartLabel(s, i)],
      [
        'Title',
        'CONSPECTUS',
        '',
        '1. INTRODUCTION',
        '2. Multiple Interactions',
        '2. Multiple Interactions \u203a 2.1. Metal-Metal',
        '',
        'Supplementary',
      ],
    );
  });

  test('design/469: the open payload applies headings to sentences', () {
    final session = ReadingSession.fromOpenJson({
      'title': 'A paper title',
      'sentences': [
        {'id': 'a1', 'text': 'First body sentence.', 'section': 'body'},
        {'id': 'a2', 'text': 'Second body sentence.', 'section': 'body'},
      ],
      'headings': [
        {'text': '2.1. Metal-Metal', 'from': 'a2'},
      ],
    });
    final heads = session.sentences.map((e) => e.heading).toList();
    expect(heads.last, '2.1. Metal-Metal');
    expect(heads.first, '');
  });

  test('design/469: the on-device copy keeps the headings', () {
    final session = ReadingSession.fromOpenJson({
      'title': 'A paper title',
      'sentences': [
        for (final s in _paper())
          {'id': s.id, 'text': 'Sentence ${s.id} here.', 'section': s.section},
      ],
      'headings': _heads,
    });
    final disk = readingSessionToPaperDiskJson(session);
    final back = ReadingSession.fromOpenJson(disk);
    expect(
      back.sentences.map((e) => e.heading).toList(),
      session.sentences.map((e) => e.heading).toList(),
    );
    expect(
      back.sentences.firstWhere((e) => e.id == 'b2').heading,
      contains('2.1. Metal-Metal'),
    );
    expect(readingSessionToPaperDiskJson(ReadingSession.fromOpenJson({
      'title': 'A paper title',
      'sentences': [
        {'id': 'a', 'text': 'Only sentence here.', 'section': 'body'},
      ],
    })).containsKey('headings'), isFalse);
  });

  test('design/470: an empty list from the server is kept, so it is asked once', () {
    final none = ReadingSession.fromOpenJson({
      'title': 'A paper title',
      'sentences': [
        {'id': 'a', 'text': 'Only sentence here.', 'section': 'body'},
      ],
      'headings': <Object>[],
    });
    expect(none.headingsKnown, isTrue);
    final disk = readingSessionToPaperDiskJson(none);
    expect(disk['headings'], isEmpty);
    expect(ReadingSession.fromOpenJson(disk).headingsKnown, isTrue);
    final old = ReadingSession.fromOpenJson({
      'title': 'A paper title',
      'sentences': [
        {'id': 'a', 'text': 'Only sentence here.', 'section': 'body'},
      ],
    });
    expect(old.headingsKnown, isFalse);
  });

  test('design/470: opening a copy without headings asks the server', () {
    final src = File('lib/state/library_controller.dart').readAsStringSync();
    final open = src.indexOf('unawaited(_backfillPaperHeadings(o));');
    final session = src.lastIndexOf('session = o;', open);
    expect(open, greaterThan(0));
    expect(session, greaterThan(0));
    final at = src.indexOf('Future<void> _backfillPaperHeadings(');
    final body = src.substring(at, src.indexOf('\n  Future<', at + 10));
    expect(body.contains('o.headingsKnown ||'), isTrue);
    expect(body.contains('_client.fetchPaperHeadings(cid)'), isTrue);
    expect(body.contains('_headingsAsked.remove(cid)'), isTrue);
    expect(body.contains('shadowPersistReadingSession(o)'), isTrue);
  });
}
