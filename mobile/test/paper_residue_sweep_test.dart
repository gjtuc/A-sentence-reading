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

  test('design/397 a paired SI folded under its main row is kept', () {
    final keep = residueKeepTokens(residueLibraryIds([
      (id: '79fddfcd83b7', mateId: 'a0e4f8691e2c'),
      (id: '6c1cc930d02f', mateId: ''),
    ]));
    final drop = residueIdsNotInKeep(
      keep: keep,
      found: ['79fddfcd83b7', 'a0e4f8691e2c', '6c1cc930d02f', 'orphanorphan'],
    );
    expect(drop, {'orphanorphan'});
  });
}
