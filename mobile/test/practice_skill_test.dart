import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
import 'package:sentence_reading/practice_skill/chunk_density.dart';
import 'package:sentence_reading/practice_skill/practice_skill_controller.dart';
import 'package:sentence_reading/practice_skill/pass_line.dart';
import 'package:sentence_reading/practice_skill/skill_adapt.dart';
import 'package:sentence_reading/practice_skill/skill_ladder.dart';
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
    // design/371 - it leaves the sheet rather than counting against the reader:
    // two words were asked about and both were right, so this is full marks.
    expect(all.score.refN, 2);
    expect(all.score.hitN, 2);
    expect(all.score.accuracy, 1.0);
    expect(all.slotHits, '-11');
    expect(all.soundPassN, 2);
    expect(all.score.missedSpans, isEmpty);
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
    // Saying nothing is a real answer worth zero, not an unanswerable question.
    // Only the two-sound word leaves the sheet, and it leaves it either way.
    expect(out.slotHits, '-00');
    expect(out.score.accuracy, 0.0);
    expect(out.score.missedSpans, hasLength(2));
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
    expect(out.score.missedSpans.map((s) => s.spoken).toList(), ['grew']);
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
    expect(out.slotPieces.split(' | '), hasLength(4));
    // design/371 - two of them are too short to ask about, so two are scored.
    expect(out.score.refN, 2);
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

  test('design/374 a cached row with no reference sound is asked again', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    // What the server sends while the reference is still being built.
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
      FollowSpan(start: 4, end: 8, weight: 4),
    ]);
    expect(cache.phoneSpanN(chunk), 0);
    // design/371 allowed one. With design/373 also spending an ask to discover a
    // stale row, one was not enough to outlast an eight-second build, and the
    // sentence went unscored for the whole run.
    for (var i = 0; i < kSoundAskMax; i++) {
      expect(cache.lacksSound(chunk), isTrue);
    }
    // The cap is what stops a build stuck in the queue being asked about every
    // time the sentence is shown.
    expect(cache.lacksSound(chunk), isFalse);
  });

  test('design/371 a row that carries the sounds stays cached', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(
        start: 4,
        end: 8,
        weight: 4,
        phone: 'f i l m',
        share: 'f=100,i=100,l=100,m=100',
      ),
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

  test('design/371 a new account is judged by the fixed line', () {
    const fresh = PassLine();
    expect(fresh.warm, isFalse);
    expect(fresh.lineOr(kPhoneOverlapMin), kPhoneOverlapMin);
    // Still cold one word short of the warmup.
    var cold = const PassLine();
    for (var i = 0; i < kPassLineWarmup - 1; i++) {
      cold = cold.after(0.8);
    }
    expect(cold.warm, isFalse);
    expect(cold.lineOr(kPhoneOverlapMin), kPhoneOverlapMin);
  });

  test('design/371 a warm account is judged a little below its own average', () {
    var line = const PassLine();
    for (var i = 0; i < kPassLineWarmup; i++) {
      line = line.after(0.8);
    }
    expect(line.warm, isTrue);
    // Every word the same, so there is no spread and the line sits on the mean.
    expect(line.avg, closeTo(0.8, 1e-9));
    expect(line.spread, closeTo(0, 1e-9));
    expect(line.lineOr(kPhoneOverlapMin), closeTo(0.8, 1e-9));
  });

  test('design/371 a reader who swings is not punished for swinging', () {
    var tight = const PassLine();
    var wide = const PassLine();
    for (var i = 0; i < 400; i++) {
      tight = tight.after(i.isEven ? 0.78 : 0.82);
      wide = wide.after(i.isEven ? 0.60 : 1.00);
    }
    // Same average, so only the spread can move the line.
    expect(wide.avg, closeTo(tight.avg, 0.02));
    expect(wide.lineOr(0.72), lessThan(tight.lineOr(0.72)));
  });

  test('design/371 the early average is a plain mean, not one word repeated', () {
    // Seeding the moving average with a single word would leave it steering the
    // line for the next three hundred.
    final line = const PassLine().after(0.2).after(0.8);
    expect(line.avg, closeTo(0.5, 1e-9));
  });

  test('design/371 only a word that could be judged moves the average', () {
    // Two sounds is under the floor, and an empty take has nothing in it. Both
    // come back below every line rather than at zero, which is a real score.
    expect(phoneOverlap('d i', const ['d i f i l m']), -1);
    expect(phoneOverlap('f i l m', const []), 0.0);
    final out = diagnoseSpokenSlots(
      display: 'The film grew',
      spoken: 'The film grew',
      spans: _spans('The film grew', [
        ['The', 4, 'd i'],
        ['film', 5, 'f i l m'],
        ['grew', 4, 'g r uu'],
      ]),
      heardPhones: const ['f i l m g r uu'],
    );
    // The is two sounds, so two words were judged, not three.
    expect(out.wordScores, hasLength(2));
    expect(out.wordScores.every((s) => s >= 0), isTrue);
  });

  test('design/371 the line the caller passes is what decides the slot', () {
    final spans = _spans('The film grew', [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
    ]);
    // film read with the wrong last sound: three of four land. design/388 —
    // this ruler is never judged under kWordOverlapLine, so the loose line is
    // that floor rather than anything lower.
    const heard = ['f i l n g r oo'];
    final strict = diagnoseSpokenSlots(
      display: 'The film grew', spoken: 'The film grew',
      spans: spans, heardPhones: heard, passLine: 0.99,
    );
    final loose = diagnoseSpokenSlots(
      display: 'The film grew', spoken: 'The film grew',
      spans: spans, heardPhones: heard, passLine: kWordOverlapLine,
    );
    expect(loose.score.hitN, greaterThan(strict.score.hitN));
  });

  test('design/371 the line does not follow a broken microphone down', () {
    // Every word scoring 0.1 would otherwise teach the account that 0.1 is
    // normal, and the app would pass everything while saying it was fine.
    var line = const PassLine();
    for (var i = 0; i < 400; i++) {
      line = line.after(i.isEven ? 0.09 : 0.11);
    }
    expect(line.avg, closeTo(0.1, 0.01));
    expect(line.lineOr(kPhoneOverlapMin), kPassLineFloor);
    // A reader who is doing fine is still judged by their own average.
    var fine = const PassLine();
    for (var i = 0; i < 400; i++) {
      fine = fine.after(i.isEven ? 0.78 : 0.82);
    }
    expect(fine.lineOr(kPhoneOverlapMin), greaterThan(kPassLineFloor));
  });

  test('design/371 a word too short to ask about does not count as wrong', () {
    const display = 'The film';
    // Two printed words. The first has two sounds, which match almost anything,
    // so there is no honest way to ask whether it was said right.
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: _spans(display, [
        ['The', 4, 'd i'],
        ['film', 4, 'f i l m'],
      ]),
      heardPhones: const ['f i l m'],
    );
    // One question asked, one right. Not one right out of two.
    expect(out.score.refN, 1);
    expect(out.score.hitN, 1);
    expect(out.score.accuracy, 1.0);
    expect(out.slotHits, '-1');
    // And it is not handed to the reader as something to practise.
    expect(out.score.missedSpans, isEmpty);
    // Nor does it teach the account a pass line it was never scored against.
    expect(out.wordScores, hasLength(1));
  });

  test('design/371 a take nobody could be asked about is not scored at all', () {
    const display = 'The a';
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: _spans(display, [
        ['The', 4, 'd i'],
        ['a', 1, 'a'],
      ]),
      heardPhones: const ['d i a'],
    );
    // Zero out of zero is not a score, and calling it all wrong would be a lie.
    expect(out.score.ok, isFalse);
    expect(out.slotCode, kSoundTooShort);
    expect(out.score.accuracy, isNull);
    expect(out.wordScores, isEmpty);
  });

  test('design/373 a stress mark means the sounds came from another reader', () {
    // The waveform model has no stress mark anywhere in its 392 tokens, so one
    // appearing can only have come from the dictionary reader design/368 cut.
    expect(soundsFromOtherReader('kˈɛmɪkə‍l'), isTrue);
    expect(soundsFromOtherReader('k ɛ m ɪ k ə l'), isFalse);
  });

  test('design/373 a tie between two halves of a vowel is the same tell', () {
    // The model writes `eɪ` as one token with nothing between the letters.
    // eSpeak joined them, and a joined pair can never equal an unjoined one.
    expect(soundsFromOtherReader('vˈe‍ɪp'), isTrue);
    expect(soundsFromOtherReader('v eɪ p'), isFalse);
    expect(soundsFromOtherReader('dˌɛp'), isTrue);
  });

  test('design/373 a cached row full of the wrong reading is asked again', () {
    final cache = SpokenCache();
    const chunk = 'Chemical vapor deposition';
    // Exactly what the phone had on disk: three words, every one with sounds,
    // and every one unscoreable. design/371 alone kept this row forever.
    cache.put(chunk, 'Chemical vapor deposition', spans: const [
      FollowSpan(start: 0, end: 8, weight: 8, phone: 'kˈɛmɪkə‍l'),
    ]);
    expect(cache.phoneSpanN(chunk), 1);
    expect(cache.staleSpanN(chunk), 1);
    expect(cache.lacksSound(chunk), isTrue);
    // And again, because the answer replacing it is still being built. Stopping
    // here is what left every sentence after the first unscored. design/374.
    expect(cache.lacksSound(chunk), isTrue);
  });

  test('design/373 a row read by the model is left alone', () {
    final cache = SpokenCache();
    const chunk = 'Chemical vapor deposition';
    cache.put(chunk, 'Chemical vapor deposition', spans: const [
      FollowSpan(
        start: 0,
        end: 8,
        weight: 8,
        phone: 'k ɛ m ɪ k ə l',
        share: 'k=100,ɛ=100,m=100,ɪ=100,k=100,ə=100,l=100',
      ),
    ]);
    expect(cache.staleSpanN(chunk), 0);
    expect(cache.lacksSound(chunk), isFalse);
  });

  test('design/373 one bad span in a row is enough to ask again', () {
    final cache = SpokenCache();
    const chunk = 'Chemical vapor deposition';
    // A sentence is asked for as a whole, so a row half-written by each reader
    // still has to be replaced; scoring the good half would report the rest as
    // misread words the speaker never got wrong.
    cache.put(chunk, 'Chemical vapor deposition', spans: const [
      FollowSpan(
        start: 0,
        end: 8,
        weight: 8,
        phone: 'k ɛ m ɪ k ə l',
        share: 'k=100,ɛ=100,m=100,ɪ=100,k=100,ə=100,l=100',
      ),
      FollowSpan(start: 9, end: 14, weight: 5, phone: 'vˈe‍ɪp'),
    ]);
    expect(cache.phoneSpanN(chunk), 2);
    expect(cache.staleSpanN(chunk), 1);
    expect(cache.lacksSound(chunk), isTrue);
  });

  test('design/374 a server with no reference coming is not asked again', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    // `empty` means the reference exists but claimed none of these words. Asking
    // again cannot change that, and design/371 would still have spent a call.
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
    ], soundRefCode: 'empty');
    expect(cache.refCode(chunk), 'empty');
    expect(cache.lacksSound(chunk), isFalse);
    expect(cache.askN(chunk), 0);
  });

  test('design/374 a build in flight earns another ask', () {
    for (final code in kSoundRefComing) {
      final cache = SpokenCache();
      const chunk = 'The film grew.';
      cache.put(chunk, 'The film grew.', spans: const [
        FollowSpan(start: 0, end: 3, weight: 3),
      ], soundRefCode: code);
      expect(cache.lacksSound(chunk), isTrue, reason: code);
    }
  });

  test('design/374 a named failure stops the asking', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    // A voice we are not allowed to use fails the same way for every sentence,
    // so one call is the whole budget it deserves.
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
    ], soundRefCode: 'permissiondenied');
    expect(cache.lacksSound(chunk), isFalse);
  });

  test('design/374 a server too old to say keeps the budget', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    // No code at all is not a refusal. Reading it as one would turn an old
    // server into a phone that never scores anything.
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
    ]);
    expect(cache.refCode(chunk), '');
    expect(cache.lacksSound(chunk), isTrue);
  });

  test('design/374 a row that gained its sounds is not asked about again', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
    ], soundRefCode: 'queued');
    expect(cache.lacksSound(chunk), isTrue);
    // The ask the server answered. Having the sounds ends it well short of the
    // cap, which is the normal path and must not cost the remaining calls.
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3, phone: 'd i', share: 'd=100,i=100'),
    ], soundRefCode: 'ready');
    expect(cache.lacksSound(chunk), isFalse);
    expect(cache.askN(chunk), 1);
  });

  test('design/374 a new speak-norm starts the budget over', () {
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 0, end: 3, weight: 3),
    ], soundRefCode: 'permissiondenied');
    expect(cache.lacksSound(chunk), isFalse);
    // The rows are thrown away, so what the server said about them cannot keep
    // deciding anything.
    cache.setSpeakNorm('v11');
    expect(cache.refCode(chunk), '');
    expect(cache.askN(chunk), 0);
  });

  test('design/375 a fresh account is judged by the cold line', () {
    const fresh = PassLine();
    expect(fresh.warm, isFalse);
    expect(fresh.lineOr(kPassLineCold), kPassLineCold);
    // design/366's 0.72 answers how close two different words are allowed to
    // sound. Used as a pass line it made the first forty words of an account the
    // hardest it is ever judged, and it dropped 38% of correctly-read words.
    expect(kPassLineCold, lessThan(kPhoneOverlapMin));
  });

  test('design/375 the review is judged by the line it is given', () {
    const target = 'f i l';
    const heard = ['d i f i n'];
    // Two of three sounds line up, so the overlap is 0.667: above the cold line
    // and below design/366's. The review has to agree with the speak phase, so
    // the line comes from the caller rather than from a constant in here.
    expect(phonesClose(target, heard, line: 0.72), isFalse);
    expect(phonesClose(target, heard), isTrue);
  });

  test('design/375 a warm account still decides for itself', () {
    // The cold line is a starting point, not a new fixed line. An account that
    // has read enough is judged by its own average and spread, exactly as before.
    var line = const PassLine();
    for (var i = 0; i < kPassLineWarmup + 5; i++) {
      line = line.after(0.90);
    }
    expect(line.warm, isTrue);
    expect(line.lineOr(kPassLineCold), closeTo(0.90, 1e-6));
  });

  test('design/377 the closeness string lines up with the hit marks', () {
    const display = 'The film grew';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
    ]);
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m g r uu'],
    );
    final scores = out.slotScores.split(' ');
    // One field per slot, in the same order, so the two strings can be read side
    // by side in a log without counting characters.
    expect(scores.length, out.slotHits.length);
    // `The` is under kPhoneMinUnits, so it was never asked. A 0 there would say
    // it was asked and scored nothing, which is a different claim.
    expect(out.slotHits, '-11');
    expect(scores.first, '-');
    expect(scores[1], '100');
    expect(scores[2], '100');
  });

  test('design/377 a refused word says how far under it sat', () {
    const display = 'The film grew';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
    ]);
    // `grew` read as something else: its sounds are not in the take.
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m b aa d'],
      passLine: 0.6,
    );
    final scores = out.slotScores.split(' ');
    expect(out.slotHits, '-10');
    // The number is the distance the marks cannot carry: this is the whole point
    // of the key, so a refusal by a hair reads differently from this one.
    final grew = int.parse(scores[2]);
    expect(grew, lessThan(60));
    expect(grew, greaterThanOrEqualTo(0));
  });

  test('design/377 every mark that was asked carries a number', () {
    const display = 'The film grew thin fast';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
      ['thin', 5, 'th i n'],
      ['fast', 4, 'f aa s t'],
    ]);
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m g r uu th i n f aa s t'],
    );
    final scores = out.slotScores.split(' ');
    expect(scores.length, out.slotHits.length);
    for (var i = 0; i < out.slotHits.length; i += 1) {
      if (out.slotHits[i] == '-') {
        expect(scores[i], '-');
      } else {
        // Hundredths, so the log never has to carry a decimal point.
        final n = int.parse(scores[i]);
        expect(n, inInclusiveRange(0, 100));
        // And the number has to agree with the mark beside it, or one of them is
        // lying and a reader cannot tell which.
        expect(n >= 72, out.slotHits[i] == '1');
      }
    }
  });

  test('design/382 the server score decides, and lines up with the slots', () {
    const display = 'The film grew thin fast';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
      ['thin', 5, 'th i n'],
      ['fast', 4, 'f aa s t'],
    ]);
    // The is two sounds long, so it cannot be asked about however sure the
    // model is. The rest are the server's own numbers, in slot order.
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m g r uu th i n f aa s t'],
      passLine: 0.60,
      soundScores: parseSlotScores('99 91 40 88 20', slotN: 5),
    );
    expect(out.slotHits, '-1010');
    expect(out.slotScores, '- 91 40 88 20');
    expect(out.score.refN, 4);
    expect(out.score.hitN, 2);
  });

  test('design/382 a row that does not fit the slots is refused whole', () {
    const display = 'The film grew thin fast';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
      ['thin', 5, 'th i n'],
      ['fast', 4, 'f aa s t'],
    ]);
    // Four numbers for five slots. Sliding by one would judge every word by its
    // neighbour's sounds, so the sounds are compared the way they shipped.
    expect(parseSlotScores('99 91 40 88', slotN: 5), isEmpty);
    expect(parseSlotScores('99 91 40 88 abc', slotN: 5), isEmpty);
    expect(parseSlotScores('99 91 40 88 200', slotN: 5), isEmpty);
    final shipped = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m g r uu th i n f aa s t'],
    );
    final refused = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      heardPhones: const ['f i l m g r uu th i n f aa s t'],
      soundScores: parseSlotScores('99 91 40 88', slotN: 5),
    );
    expect(refused.slotHits, shipped.slotHits);
    expect(refused.slotScores, shipped.slotScores);
  });

  test('design/382 the slots we ask with are the slots we score', () {
    const display = 'The film, grew thin.';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film,', 6, 'f i l m'],
      ['grew', 5, 'g r uu'],
      ['thin.', 5, 'th i n'],
    ]);
    final asked = slotPhonesFor(
      display: display,
      spoken: 'The film, grew thin.',
      spans: spans,
    );
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: 'The film, grew thin.',
      spans: spans,
      heardPhones: const ['f i l m g r uu th i n'],
      soundScores: parseSlotScores(
        List.filled(asked.length, '90').join(' '),
        slotN: asked.length,
      ),
    );
    // One number per slot, and every slot that was asked carries one.
    expect(asked.length, out.slotScores.split(' ').length);
    expect(asked.length, out.slotHits.length);
  });

  test('design/387 ten sounds at 40 percent fail the hard bar and the line', () {
    final score = twoGateWordScore(
      probs: List<double>.filled(10, 0.40),
      soundN: 10,
      said: 10,
      bar: 0.70,
      line: 0.57,
    );
    expect(score, 0);
  });

  test('design/387 an extra sound still sits in the divisor', () {
    final score = twoGateWordScore(
      probs: const [0.90, 0.90, 0.90],
      soundN: 3,
      said: 4,
      bar: 0.70,
      line: 0.57,
    );
    expect(score, closeTo(0.75, 1e-9));
  });

  test('design/386 a share row is sent only when it lines up', () {
    const display = 'The film grew';
    const spoken = display;
    final spans = [
      const FollowSpan(start: 0, end: 3, weight: 3, phone: 'd i', share: 'd,i'),
      const FollowSpan(
        start: 4,
        end: 8,
        weight: 4,
        phone: 'f i l m',
        share: 'f,i,l,m',
      ),
      const FollowSpan(
        start: 9,
        end: 13,
        weight: 4,
        phone: 'g r uu',
        share: 'g,r,uu',
      ),
    ];
    expect(
      slotSharesFor(display: display, spoken: spoken, spans: spans),
      ['d,i', 'f,i,l,m', 'g,r,uu'],
    );
    final missing = [
      spans[0],
      const FollowSpan(start: 4, end: 8, weight: 4, phone: 'f i l m'),
      spans[2],
    ];
    expect(
      slotSharesFor(display: display, spoken: spoken, spans: missing),
      isEmpty,
    );
  });

  test('design/388 the bar is 20 plus the rung, in percent', () {
    expect(skillDifficultyBar(tier: 0, density: 2), closeTo(0.21, 1e-9));
    expect(skillDifficultyBar(tier: 4, density: -2), closeTo(0.45, 1e-9));
    expect(skillDifficultyBar(tier: 9, density: -2), closeTo(0.70, 1e-9));
  });

  test('design/388 one native symbol over the bar decides stage one', () {
    // Native a 60, b 10, c 15, d 15 at rung 25. Only a is at 20% or more.
    const bar = 0.45;
    const line = 0.57;
    expect(
      soundClears(0.30, top: const [SoundTop(0.60, 0.50)], bar: bar, line: line),
      isTrue,
    );
    // Under the bar on a: stage two, the overlap against the line.
    expect(
      soundClears(0.30, top: const [SoundTop(0.60, 0.30)], bar: bar, line: line),
      isFalse,
    );
    expect(
      soundClears(0.60, top: const [SoundTop(0.60, 0.30)], bar: bar, line: line),
      isTrue,
    );
  });

  test('design/388 no native symbol at the bar goes straight to the line', () {
    // Native a, b, c, d at 25% each. Nothing reaches 45%, so stage one has
    // nothing to ask and the overlap decides.
    const even = [
      SoundTop(0.25, 0.50),
      SoundTop(0.25, 0.50),
      SoundTop(0.25, 0),
      SoundTop(0.25, 0),
    ];
    expect(soundClears(0.50, top: even, bar: 0.45, line: 0.50), isTrue);
    expect(soundClears(0.25, top: even, bar: 0.45, line: 0.50), isFalse);
    expect(soundClears(0.40, top: even, bar: 0.45, line: 0.50), isFalse);
  });

  test('design/388 every native symbol at the bar has to be met', () {
    const split = [SoundTop(0.50, 0.70), SoundTop(0.46, 0.20)];
    expect(soundClears(0.40, top: split, bar: 0.45, line: 0.57), isFalse);
    // Both met: stage one passes however small the overlap came out.
    const both = [SoundTop(0.50, 0.50), SoundTop(0.46, 0.46)];
    expect(soundClears(0.10, top: both, bar: 0.45, line: 0.57), isTrue);
  });

  test('design/388 no pairs at all is the line alone', () {
    expect(soundClears(0.25, bar: 0.21, line: 0.57), isFalse);
    expect(soundClears(0.60, bar: 0.70, line: 0.57), isTrue);
  });

  test('design/388 the pair row lines up or is refused whole', () {
    final got = parseSlotTops('95:90,60:30 30:10,|-', slotN: 2);
    expect(got, hasLength(2));
    expect(got[0], hasLength(3));
    expect(got[0][0].single.native, closeTo(0.95, 1e-9));
    expect(got[0][1], hasLength(2));
    expect(got[0][1][1].reader, closeTo(0.10, 1e-9));
    expect(got[0][2], isEmpty);
    expect(got[1], isEmpty);
    expect(parseSlotTops('95:90|-', slotN: 3), isEmpty);
    expect(parseSlotTops('95-90|-', slotN: 2), isEmpty);
    expect(parseSlotTops('95:190|-', slotN: 2), isEmpty);
    expect(parseSlotTops('', slotN: 1), isEmpty);
  });

  test('design/388 pairs that do not line up leave the word to the line', () {
    final score = twoGateWordScore(
      probs: const [0.30, 0.30],
      tops: const [
        [SoundTop(0.9, 0.9)],
      ],
      soundN: 2,
      said: 2,
      bar: 0.45,
      line: 0.57,
    );
    expect(score, 0);
  });

  test('design/388 the line learns each sound, not each word', () {
    const display = 'The film grew thin fast';
    final spans = _spans(display, [
      ['The', 4, 'd i'],
      ['film', 5, 'f i l m'],
      ['grew', 4, 'g r uu'],
      ['thin', 5, 'th i n'],
      ['fast', 4, 'f aa s t'],
    ]);
    final out = diagnoseSpokenSlots(
      display: display,
      spoken: display,
      spans: spans,
      passLine: 0.60,
      soundScores: parseSlotScores('99 91 40 88 20', slotN: 5),
      soundEach: parseSlotSounds(
        '99 99|90 91 92 93|40 41 42|88 87 86|20 21 22 23',
        slotN: 5,
      ),
    );
    // The is under the floor. The other four hold 4 + 3 + 3 + 4 sounds.
    expect(out.wordScores, hasLength(14));
    expect(out.wordScores.first, closeTo(0.90, 1e-9));
    expect(out.wordScores.last, closeTo(0.23, 1e-9));
  });

  test('design/388 a line stored under another unit starts cold', () {
    final old = SkillState.fromJson({
      'line_avg': 0.8,
      'line_var': 0.01,
      'line_n': 500,
    });
    expect(old.line.n, 0);
    final kept = SkillState.fromJson({
      'line_avg': 0.8,
      'line_var': 0.01,
      'line_n': 500,
      'line_unit': kPassLineUnit,
    });
    expect(kept.line.n, 500);
    expect(SkillState.fromJson(kept.toJson()).line.n, 500);
  });

  test('design/388 sounds with no native spread beside them are stale', () {
    expect(spreadMissing('f i l m', ''), isTrue);
    expect(spreadMissing('f i l m', 'f,i,l,m'), isTrue);
    expect(spreadMissing('f i l m', 'f=100,i=100,l=100,m=100'), isFalse);
    expect(spreadMissing('', ''), isFalse);
    final cache = SpokenCache();
    const chunk = 'The film grew.';
    cache.put(chunk, 'The film grew.', spans: const [
      FollowSpan(start: 4, end: 8, weight: 4, phone: 'f i l m', share: 'f,i,l,m'),
    ]);
    expect(cache.staleSpanN(chunk), 1);
    expect(cache.lacksSound(chunk), isTrue);
  });

  test('design/388 the cold line is the formula with the population numbers', () {
    // Spread overlap over all 16,759 sounds of real reading the scorer could
    // ask about, measured without looking at a label:
    // scripts/spread_overlap_probe.py.
    const mean = 0.680;
    const spread = 0.370;
    const fromFormula = mean + kPassLineOffset * spread;
    // Single sounds land near 0 or near 1, so the formula is under the floor
    // and the floor is the line, as it would be for an account reading so.
    expect(fromFormula, lessThan(kPassLineFloor));
    // Tying the constant to the measurement means moving it needs the
    // measurement redone rather than a number someone liked better.
    expect(kPassLineCold, closeTo(math.max(fromFormula, kPassLineFloor), 1e-9));
  });

  test('design/388 the warm-up is still forty words, counted in sounds', () {
    // design/375's band, in words: scripts/warmup_probe.py found no knee, and
    // under 28 or over 86 the answer is obviously wrong.
    final words = kPassLineWarmup / kPassLineSoundsPerWord;
    expect(words, closeTo(40, 0.5));
    expect(words, greaterThanOrEqualTo(28));
    expect(words, lessThan(86));
    expect(kPassLineWeight * kPassLineSoundsPerWord, closeTo(0.01, 1e-12));
  });

  test('design/388 the handover is flat, which is why 40 need not be exact', () {
    // The account's own line at the warm-up, median over 400 orderings of the
    // same words. It sits on the cold line, so crossing over is not an event
    // the reader can feel. If anyone raises the cold line, this says why.
    const ownLineAtWarmup = 0.450;
    expect((ownLineAtWarmup - kPassLineCold).abs(), lessThan(0.02));
    expect(kPassLineCold, lessThan(ownLineAtWarmup + 0.02));
  });
}
