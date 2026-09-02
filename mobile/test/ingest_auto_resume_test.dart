import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/state/ingest_auto_resume.dart';

void main() {
  group('normalizeIngestStageKey', () {
    test('strips fractions and digits so same stage matches', () {
      final a = normalizeIngestStageKey('처리 중 27% · 페이지 이미지 읽는 중 6/12 · 클라우드');
      final b = normalizeIngestStageKey('처리 중 31% · 페이지 이미지 읽는 중 8/12 · 클라우드');
      expect(a, b);
      expect(a.contains('페이지'), isTrue);
    });

    test('empty stage uses percent band', () {
      expect(normalizeIngestStageKey('', percent: 27), 'pct_20');
    });
  });

  group('IngestAutoResumeGate', () {
    test('auto up to 3 consecutive same stage then stop', () {
      final g = IngestAutoResumeGate();
      expect(g.noteTimeout('조각 올리는 중'), isTrue);
      expect(g.consecutiveTimeouts, 1);
      expect(g.noteTimeout('조각 올리는 중'), isTrue);
      expect(g.noteTimeout('조각 올리는 중'), isTrue);
      expect(g.consecutiveTimeouts, 3);
      expect(g.noteTimeout('조각 올리는 중'), isFalse);
      expect(g.consecutiveTimeouts, 4);
    });

    test('new stage resets streak', () {
      final g = IngestAutoResumeGate();
      expect(g.noteTimeout('조각 올리는 중'), isTrue);
      expect(g.noteTimeout('조각 올리는 중'), isTrue);
      expect(g.noteTimeout('조각 올리는 중'), isTrue);
      expect(g.noteTimeout('이미지 다듬는 중'), isTrue);
      expect(g.consecutiveTimeouts, 1);
      expect(g.stageKey, '이미지 다듬는 중');
    });

    test('progress to other stage clears streak', () {
      final g = IngestAutoResumeGate();
      g.noteTimeout('조각 올리는 중');
      g.noteTimeout('조각 올리는 중');
      g.noteProgress('이미지 다듬는 중');
      expect(g.consecutiveTimeouts, 0);
      expect(g.noteTimeout('이미지 다듬는 중'), isTrue);
      expect(g.consecutiveTimeouts, 1);
    });
  });
}
