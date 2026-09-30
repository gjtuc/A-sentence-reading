import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
import 'package:sentence_reading/practice_skill/chunk_density.dart';
import 'package:sentence_reading/practice_skill/practice_skill_controller.dart';
import 'package:sentence_reading/practice_skill/skill_adapt.dart';
import 'package:sentence_reading/practice_skill/skill_score.dart';
import 'package:sentence_reading/practice_skill/skill_store.dart';

/// design/370 - a slot is judged by sound. `phone` on a span carries the sounds
/// the native voice makes for that word, and `heardPhones` carries the run the
/// waveform model heard. Symbols here are plain letters on purpose: the compare
/// counts units, so ascii reads the same as IPA and keeps the test legible.
List<FollowSpan> _spans(String display, List<List<Object>> rows) => [
      for (final row in rows)
        FollowSpan(
          start: display.indexOf(row[0] as String),
          end: display.indexOf(row[0] as String) + (row[0] as String).length,
          weight: row[1] as int,
          phone: row[2] as String,
        ),
    ];

void main() {
  test('effectiveChunks finer inserts mid prefix', () {
    final base = [
      'The catalyst',
      'The catalyst was prepared by reduction',
    ];
    final out = effectiveChunks(base, 1);
    expect(out.length, greaterThan(base.length));
    expect(out.last, base.last);
  });

  test('epoch wait until target block means', () {
    final state = SkillState(
      epochMeans: const [0.5, 0.5, 0.5],
      epochTargetN: 5,
      density: 0,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.reason, 'epoch_wait');
    expect(d.densityDelta, 0);
  });

  test('epoch finer when avg <= 80 and can finer', () {
    final state = SkillState(
      epochMeans: const [0.7, 0.7, 0.7, 0.7, 0.7],
      epochTargetN: 5,
      density: 0,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.densityDelta, 1);
    expect(d.reason, 'finer');
  });

  test('epoch coarser when avg >= 90', () {
    final state = SkillState(
      epochMeans: const [0.95, 0.92, 0.91, 0.90, 0.93],
      epochTargetN: 5,
      density: 1,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.densityDelta, -1);
    expect(d.reason, 'coarser');
  });

  test('epoch hold in 80-90 band', () {
    final state = SkillState(
      epochMeans: const [0.85, 0.85, 0.85, 0.85, 0.85],
      epochTargetN: 5,
      density: 0,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.reason, 'hold');
    expect(d.densityDelta, 0);
  });

  test('rollSkillEpochTarget in 5..10', () {
    for (var i = 0; i < 40; i++) {
      final n = rollSkillEpochTarget();
      expect(n, inInclusiveRange(5, 10));
    }
  });

  test('design/370 a take with no reference sounds is not scored', () {
    const display = 'The film is thin';
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      // Spans with no `phone`: nothing to compare against.
      spans: const [
        FollowSpan(start: 0, end: 3, weight: 3),
        FollowSpan(start: 4, end: 8, weight: 5),
      ],
      heardPhones: const ['d i f i l m'],
    );
    // Calling this 0% would blame the reader for a missing reference.
    expect(out.score.ok, isFalse);
    expect(out.score.error, kSoundRefMissing);
    expect(out.score.accuracy, isNull);
    expect(out.slotCode, kSoundRefMissing);
  });

  test('design/370 a word is judged by its sounds, not by its letters', () {
    const display = 'The film grew';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
    ]);
    final all = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m g r uu'],
    );
    expect(all.score.ok, isTrue);
    // `The` is two units, under kPhoneMinUnits, so sound cannot judge it.
    expect(all.score.refN, 3);
    expect(all.score.hitN, 2);
    expect(all.slotHits, '011');
    expect(all.soundPassN, 2);
    expect(all.score.missedSpans.single.spoken, 'the');
  });

  test('design/370 a silent take misses every slot it could judge', () {
    const display = 'The film grew';
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: _spans(display, [
        ['The', 4, 'd i'],
        ['film', 5, 'f i l m'],
        ['grew', 4, 'g r uu'],
      ]),
      heardPhones: const [],
    );
    expect(out.score.ok, isTrue);
    expect(out.score.hitN, 0);
    expect(out.slotHits, '000');
    expect(out.score.missedSpans, hasLength(3));
  });

  test('design/370 the review asks for the printed word, not its sounds', () {
    const display = 'The film grew';
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: _spans(display, [
        ['The', 4, 'd i'],
        ['film', 5, 'f i l m'],
        ['grew', 4, 'g r uu'],
      ]),
      heardPhones: const ['f i l m'],
    );
    // The reader has to be asked for a word they can say, not for symbols.
    expect(out.slotPieces, 'the | film | grew');
    expect(out.score.missedSpans.map((s) => s.spoken).toList(), ['the', 'grew']);
  });

  test('a printed word spoken as letters is still one slot', () {
    const display = 'CVD is a technique';
    const spoken = 'c v d is a technique';
    final spans = [
      const FollowSpan(start: 0, end: 3, weight: 5, phone: 's i d i'),
      FollowSpan(
        start: display.indexOf('is'),
        end: display.indexOf('is') + 2,
        weight: 2,
        phone: 'i z',
      ),
      FollowSpan(
        start: display.indexOf('a '),
        end: display.indexOf('a ') + 1,
        weight: 1,
        phone: 'a',
      ),
      FollowSpan(
        start: display.indexOf('technique'),
        end: display.length,
        weight: 'technique'.length,
        phone: 't e k n ii k',
      ),
    ];
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: spoken,
      spans: spans,
      heardPhones: const ['t e k n ii k'],
    );
    // Four printed words, four slots, even though one is read as three letters.
    expect(out.score.refN, 4);
    expect(out.score.hitN, 1);
    expect(
      display.substring(
        out.score.missedSpans.first.start,
        out.score.missedSpans.first.end,
      ),
      'CVD',
    );
  });

  test('marks between words do not shift the next slot', () {
    const display = 'Heat, then cool.';
    const spoken = 'heat, then cool.';
    final spans = [
      const FollowSpan(start: 0, end: 4, weight: 4, phone: 'h ii t'),
      FollowSpan(
        start: display.indexOf('then'),
        end: display.indexOf('then') + 4,
        weight: 4,
        phone: 'd e n',
      ),
      FollowSpan(
        start: display.indexOf('cool'),
        end: display.indexOf('cool') + 4,
        weight: 4,
        phone: 'k uu l',
      ),
    ];
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: spoken,
      spans: spans,
      heardPhones: const ['h ii t d e n k uu l'],
    );
    // A comma must not become the first letters of the next slot.
    expect(out.score.refN, 3);
    expect(out.score.hitN, 3);
    expect(out.slotPieces, 'heat | then | cool');
  });

  test('empty pairing reports the walk step that failed', () {
    final none = diagnoseSpokenSlots(
      display: 'Alpha beta',
      spoken: 'alpha beta',
      spans: const [],
      heardPhones: const ['a l f a'],
    );
    expect(none.score.ok, isFalse);
    expect(none.slotCode, 'no_spans');
    expect(none.spanN, 0);
    expect(none.posSpanN, 0);
  });

  test('a word run is cut into single sounds before it is compared', () {
    expect(phoneUnits('dɪspˈɜːʃən').length, greaterThan(4));
    expect(phoneUnits('t͡ʃ'), hasLength(1));
    expect(phoneUnits(''), isEmpty);
  });

  test('design/366 a word is found inside the whole run of sounds', () {
    // The target sits in the middle, so an end-to-end compare would miss it.
    expect(phonesClose('f i l m', const ['d i f i l m g r uu']), isTrue);
    expect(phonesClose('f i l m', const ['d i', 'f i l m', 'g r uu']), isTrue);
    expect(phonesClose('z z z z', const ['d i f i l m']), isFalse);
  });

  test('design/366 a short target is not judged by sound', () {
    // Two sounds match almost anything, so `the` cannot be judged this way.
    expect(phoneUnits('d i'), hasLength(2));
    expect(phonesClose('d i', const ['d i f i l m']), isFalse);
  });

  test('design/366 the window allows one split sound', () {
    // The model splits a sound in two more often than it drops one.
    expect(bestWindowOverlap(
      const ['f', 'i', 'l', 'm'],
      const ['f', 'i', 'l', 'l', 'm'],
    ), greaterThanOrEqualTo(kPhoneOverlapMin));
  });

  test('design/371 a cached row with no reference sound is asked again, once', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    // What the server sends while the reference is still being built.
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
      FollowSpan(start: 4, end: 8, weight: 4),
    ]);
    expect(cache.phoneSpanN(chunk), 0);
    expect(cache.lacksSound(chunk), isTrue);
    // Asked once. A server that can never build a reference must not cost a
    // call every time the sentence is shown.
    expect(cache.lacksSound(chunk), isFalse);
  });

  test('design/371 a row that carries the sounds stays cached', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 4, end: 8, weight: 4, phone: 'f i l m'),
    ]);
    expect(cache.phoneSpanN(chunk), 1);
    expect(cache.lacksSound(chunk), isFalse);
  });

  test('design/371 a row with no spans at all is not asked again', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    // No spans is an alignment failure. Asking again produces none either.
    cache.put(chunk, 'The film grew.', spans: const []);
    expect(cache.lacksSound(chunk), isFalse);
  });
}
