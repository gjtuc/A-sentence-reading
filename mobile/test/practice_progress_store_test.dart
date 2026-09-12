import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/practice_progress_store.dart';

void main() {
  test('prefs key uid scope', () {
    expect(practiceProgressPrefsKey(null), kPracticeProgressPrefsKeyBase);
    expect(practiceProgressPrefsKey('u1'), '$kPracticeProgressPrefsKeyBase.u.u1');
  });

  test('clamp rejects out of range sentence', () {
    expect(
      clampPracticeProgress(
        raw: const PracticeProgressRow(sentenceIndex: 99),
        sentenceCount: 10,
      ),
      isNull,
    );
  });

  test('clamp keeps valid sentence and caps chunk', () {
    final r = clampPracticeProgress(
      raw: const PracticeProgressRow(
        sentenceIndex: 3,
        chunkIndex: 9,
        sectionLabel: 'Intro 1/5',
      ),
      sentenceCount: 10,
      chunkCount: 2,
    );
    expect(r!.sentenceIndex, 3);
    expect(r.chunkIndex, 1);
    expect(r.sectionLabel, 'Intro 1/5');
  });
}
