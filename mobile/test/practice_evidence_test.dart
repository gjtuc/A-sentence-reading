import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_evidence/practice_cycle_probe.dart';
import 'package:sentence_reading/practice_evidence/practice_evidence_encode.dart';

void main() {
  test('safePracticeDetails keeps numbers drops free text', () {
    final out = safePracticeDetails({
      'schema_v': 1,
      'corr': 0.84721,
      'chunk_key': '12:3',
      'mic_code': 'mic_start',
      'BadKey': 1,
      'msg': 'Hello world',
      'ok_flag': true,
    });
    expect(out['schema_v'], 1);
    expect(out['corr'], 0.847);
    expect(out.containsKey('chunk_key'), isFalse);
    expect(out['mic_code'], 'mic_start');
    expect(out.containsKey('BadKey'), isFalse);
    expect(out.containsKey('msg'), isFalse);
    expect(out['ok_flag'], isTrue);
  });

  test('probe markComplete sets complete when take ok', () {
    final p = PracticeCycleProbe(
      cacheId: 'c1',
      sentenceId: 1,
      chunkIndex: 0,
      cycleSeq: 1,
    );
    p.markListen(ms: 2000, bytes: 10000, voiceHash: 1);
    p.markSpeak(
      wallMs: 3000,
      padMs: 2000,
      micCode: 'ok',
      takeOk: true,
      takeBytes: 12000,
      takeDurMs: 2800,
      persistOk: true,
      cloudTakeOk: false,
    );
    p.markComplete();
    final d = p.toDetails();
    expect(d['outcome'], 'complete');
    expect(d['take_ok'], 1);
    expect(d['bytes_ratio'], isNotNull);
  });

  test('buildPracticeCycleEvent envelope', () {
    final ev = buildPracticeCycleEvent(
      details: {'schema_v': 1, 'sentence_id': 2},
      cacheId: 'abc',
      appVersion: '0.3.209',
      traceId: 'tr_0123456789abcdef',
      sessionId: 'ses_0123456789ab',
      code: 'complete',
      ok: true,
    );
    expect(ev['kind'], 'practice_cycle_wide');
    expect((ev['details'] as Map)['schema_v'], 1);
  });
}
