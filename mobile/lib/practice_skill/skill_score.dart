/// design/212 — content-word multiset coverage (mirrors practice_skill_score.py).
library;

const int kContentWordListV = 1;

const Set<String> kFunctionWords = {
  'a', 'an', 'the', 'and', 'or', 'but', 'if', 'in', 'on', 'at', 'to', 'for',
  'of', 'as', 'by', 'with', 'from', 'into', 'onto', 'over', 'under', 'is',
  'are', 'was', 'were', 'be', 'been', 'being', 'am', 'do', 'does', 'did',
  'have', 'has', 'had', 'will', 'would', 'shall', 'should', 'can', 'could',
  'may', 'might', 'must', 'that', 'this', 'these', 'those', 'it', 'its',
  'they', 'them', 'their', 'we', 'our', 'you', 'your', 'he', 'she', 'his',
  'her', 'i', 'me', 'my', 'not', 'no', 'nor', 'so', 'than', 'then', 'there',
  'here', 'when', 'where', 'which', 'who', 'whom', 'what', 'how', 'also',
  'just', 'only', 'very', 'too', 'up', 'out', 'about', 'such', 'per',
};

final RegExp _tagRe = RegExp(r'<[^>]+>');
final RegExp _punctRe = RegExp(r"[^\w\s']+", unicode: true);
final RegExp _spaceRe = RegExp(r'\s+');

String normalizeSkillText(String? text) {
  if (text == null) return '';
  var t = _tagRe.allMatches(text).isEmpty
      ? text
      : text.replaceAll(_tagRe, ' ');
  t = t.toLowerCase().replaceAll('\u2019', "'").replaceAll('\u2018', "'");
  t = t.replaceAll(_punctRe, ' ');
  t = t.replaceAll(_spaceRe, ' ').trim();
  return t;
}

List<String> tokenizeSkill(String? text) {
  final n = normalizeSkillText(text);
  if (n.isEmpty) return const [];
  return n.split(' ');
}

List<String> contentWords(String? text) {
  return tokenizeSkill(text)
      .where((w) => w.isNotEmpty && !kFunctionWords.contains(w))
      .toList(growable: false);
}

class SkillScoreResult {
  const SkillScoreResult({
    required this.ok,
    this.accuracy,
    this.refN = 0,
    this.hitN = 0,
    this.error,
    this.listV = kContentWordListV,
  });

  final bool ok;
  final double? accuracy;
  final int refN;
  final int hitN;
  final String? error;
  final int listV;
}

SkillScoreResult contentWordCoverage(String? expectedSpoken, String? heard) {
  final ref = contentWords(expectedSpoken);
  final hyp = contentWords(heard);
  if (ref.isEmpty) {
    return const SkillScoreResult(
      ok: false,
      error: 'empty_content_ref',
    );
  }
  final need = <String, int>{};
  for (final w in ref) {
    need[w] = (need[w] ?? 0) + 1;
  }
  final have = <String, int>{};
  for (final w in hyp) {
    have[w] = (have[w] ?? 0) + 1;
  }
  var hit = 0;
  for (final e in need.entries) {
    final h = have[e.key] ?? 0;
    hit += h < e.value ? h : e.value;
  }
  final acc = hit / ref.length;
  return SkillScoreResult(
    ok: true,
    accuracy: (acc * 10000).round() / 10000.0,
    refN: ref.length,
    hitN: hit,
  );
}
