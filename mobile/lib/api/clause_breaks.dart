/// design/444 — a long sentence shown in its pieces.
///
/// A paper's sentence can run nine phone lines, wrapped wherever the width ran out,
/// so the shape of the sentence (main clause, a which-clause, a list of four) is
/// hidden. This picks the spaces where a reader would pause and the reader turns
/// each into a line break. A space and a line break are one character each, so
/// highlight offsets on the plain text do not move.
library;

/// Shorter sentences fit in two or three lines and are left as they are.
const int kClauseMinSentence = 120;

/// A piece shorter than this reads as a fragment, so its break is dropped.
const int kClauseMinPiece = 25;
const int kClauseMinTail = 15;

/// Words that open a new clause after a comma.
const Set<String> kClauseWords = {
  'which',
  'where',
  'whereas',
  'while',
  'although',
  'though',
  'because',
  'but',
  'including',
  'such',
  'thereby',
  'resulting',
  'leading',
  'indicating',
  'suggesting',
  'demonstrating',
  'revealing',
  'confirming',
  'enabling',
  'yielding',
};

const List<String> _roman = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'];

final _enumRe = RegExp(r'\(([ivx]{1,4}|[a-h]|[1-9])\)(?=\s)');
final _wordRe = RegExp(r'[A-Za-z]+');

/// (kind, ordinal) of a list mark, or null.
(String, int)? _mark(String label) {
  final r = _roman.indexOf(label);
  if (r >= 0) return ('roman', r + 1);
  if (RegExp(r'^[a-h]$').hasMatch(label)) {
    return ('letter', label.codeUnitAt(0) - 'a'.codeUnitAt(0) + 1);
  }
  final d = int.tryParse(label);
  if (d != null) return ('digit', d);
  return null;
}

/// Bracket depth before each character.
List<int> _depths(String s) {
  final out = List<int>.filled(s.length, 0);
  var d = 0;
  for (var i = 0; i < s.length; i++) {
    out[i] = d;
    final c = s[i];
    if (c == '(' || c == '[') d++;
    if ((c == ')' || c == ']') && d > 0) d--;
  }
  return out;
}

/// Spaces before a numbered list `(i) … (ii) …` printed at the top level.
///
/// The marks must count up from one. Two marks with no comma between them is
/// how a paper points at panels, `shown in (a) and (b)`, so that takes three or
/// a comma before a later mark.
List<int> _listBreaks(String s, List<int> depth) {
  final marks = <String, List<(int, int, bool)>>{};
  for (final m in _enumRe.allMatches(s)) {
    final at = m.start;
    if (at < 1 || s[at - 1] != ' ' || depth[at] != 0) continue;
    final mark = _mark(m.group(1)!);
    if (mark == null) continue;
    final comma = at >= 2 && s[at - 2] == ',';
    marks.putIfAbsent(mark.$1, () => []).add((at - 1, mark.$2, comma));
  }
  final out = <int>[];
  for (final list in marks.values) {
    var next = 1;
    final run = <(int, int, bool)>[];
    for (final item in list) {
      if (item.$2 == next) {
        run.add(item);
        next++;
      }
    }
    if (run.length < 2) continue;
    final commas = run.skip(1).any((e) => e.$3);
    if (run.length < 3 && !commas) continue;
    out.addAll(run.map((e) => e.$1));
  }
  return out;
}

/// Plain-text offsets of the spaces to show as line breaks.
Set<int> clauseBreakOffsets(String plain) {
  if (plain.length < kClauseMinSentence) return const {};
  final depth = _depths(plain);
  final candidates = <int>{..._listBreaks(plain, depth)};
  for (var i = 0; i + 1 < plain.length; i++) {
    final c = plain[i];
    if ((c != ',' && c != ';') || plain[i + 1] != ' ' || depth[i] != 0) continue;
    if (c == ';') {
      candidates.add(i + 1);
      continue;
    }
    final word = _wordRe.matchAsPrefix(plain, i + 2)?.group(0);
    if (word != null && kClauseWords.contains(word.toLowerCase())) {
      candidates.add(i + 1);
    }
  }
  final sorted = candidates.toList()..sort();
  final out = <int>{};
  var last = 0;
  for (final b in sorted) {
    if (b - last < kClauseMinPiece) continue;
    if (plain.length - b < kClauseMinTail) continue;
    out.add(b);
    last = b;
  }
  return out;
}

/// [plain] with the chosen spaces turned into line breaks.
String withClauseBreaks(String plain, Set<int> breaks) {
  if (breaks.isEmpty) return plain;
  final chars = plain.split('');
  for (final b in breaks) {
    if (b >= 0 && b < chars.length && chars[b] == ' ') chars[b] = '\n';
  }
  return chars.join();
}
