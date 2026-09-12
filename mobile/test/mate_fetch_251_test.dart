import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/mate_fetch/validate.dart';
import 'package:sentence_reading/mate_fetch/orchestrator.dart';
import 'package:sentence_reading/mate_fetch/fetch.dart';
import 'package:sentence_reading/api/document_citation.dart';

void main() {
  test('validateMateBytes accepts PDF magic', () {
    final r = validateMateBytes([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31]);
    expect(r.ok, isTrue);
  });

  test('validateMateBytes rejects HTML', () {
    final r = validateMateBytes('<!DOCTYPE html><html>'.codeUnits);
    expect(r.code, MateValidateCode.html);
  });

  test('mateHostAllowed allowlist', () {
    expect(mateHostAllowed('pubs.acs.org'), isTrue);
    expect(mateHostAllowed('sci-hub.se'), isFalse);
  });

  test('extractAcsSiStemFromText', () {
    expect(
      extractAcsSiStemFromText(
        'see 10.1021/acsami.2c04149/suppl_file/am2c04149_si_001.pdf end',
      ),
      'am2c04149',
    );
  });

  test('extractDoiFromText strips suppl_file', () {
    expect(
      extractDoiFromText(
        'doi:10.1021/acsami.2c04149/suppl_file/am2c04149_si_001.pdf',
      ),
      '10.1021/acsami.2c04149',
    );
  });

  test('orchestrateMateFetch absent short-circuits', () async {
    final r = await orchestrateMateFetch(
      meta: const MateResolveMeta(
        ok: true,
        siStatus: 'absent',
        fallbackBrowser: 'https://doi.org/10.1021/x',
      ),
      doi: '10.1021/x',
      want: 'si',
      fetchBytes: (_) async => const MateFetchOutcome(ok: false, code: 'skip'),
    );
    expect(r.mode, MateOrchestrateMode.absent);
  });
}
