import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/paper_residue.dart';

void main() {
  test('design/307 residue keep tokens hide live folders', () {
    final keep = residueKeepTokens(['08e20fb5d95c', 'deaddeaddead']);
    expect(keep, contains('08e20fb5d95c'));
    final drop = residueIdsNotInKeep(
      keep: keep,
      found: ['08e20fb5d95c', 'orphanorphan', 'deaddeaddead'],
    );
    expect(drop, {'orphanorphan'});
  });
}
