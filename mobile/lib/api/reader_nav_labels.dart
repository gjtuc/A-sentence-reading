/// Reader chrome labels — section-local sentence index + slot figure/table (design/151).
library;

import 'fig_refs.dart';
import 'reading_models.dart';

const _sectionLabels = <String, String>{
  'title': 'Title',
  'abstract': 'Abstract',
  'introduction': 'Introduction',
  'methods': 'Methods',
  'experimental': 'Experimental',
  'results': 'Results',
  'discussion': 'Discussion',
  'conclusion': 'Conclusion',
  'body': 'Body',
  'supplementary': 'Supplementary',
};

String sectionDisplayName(String? section) {
  final key = (section ?? '').trim().toLowerCase();
  if (key.isEmpty) return '';
  return _sectionLabels[key] ?? _titleCase(key.replaceAll('_', ' '));
}

String _titleCase(String s) {
  if (s.isEmpty) return s;
  return s.split(' ').map((w) {
    if (w.isEmpty) return w;
    return '${w[0].toUpperCase()}${w.substring(1)}';
  }).join(' ');
}

/// Header split: left = section name, right = position within section.
class SectionHeaderParts {
  const SectionHeaderParts({
    required this.sectionName,
    required this.position,
    required this.total,
  });

  final String sectionName;
  final int position;
  final int total;

  String get rightLabel => total > 0 ? '$position / $total' : '— / —';
}

/// Maps each sentence global index → position within its section.
class SectionNavIndex {
  SectionNavIndex._({
    required List<(String, int, int)> byGlobal,
    required List<String> sectionKeysInOrder,
    required Map<String, List<int>> indicesBySection,
  })  : _byGlobal = byGlobal,
        _sectionKeysInOrder = sectionKeysInOrder,
        _indicesBySection = indicesBySection;

  factory SectionNavIndex.fromSentences(List<SentenceView> sentences) {
    final buckets = <String, List<int>>{};
    final order = <String>[];
    for (var i = 0; i < sentences.length; i++) {
      final key = _sectionKey(sentences[i].section);
      if (!buckets.containsKey(key)) {
        order.add(key);
        buckets[key] = [];
      }
      buckets[key]!.add(i);
    }
    final byGlobal = List<(String, int, int)>.filled(
      sentences.length,
      ('', 0, 0),
    );
    for (final key in order) {
      final indices = buckets[key]!;
      final total = indices.length;
      for (var pos = 0; pos < indices.length; pos++) {
        byGlobal[indices[pos]] = (key, pos + 1, total);
      }
    }
    return SectionNavIndex._(
      byGlobal: byGlobal,
      sectionKeysInOrder: order,
      indicesBySection: buckets,
    );
  }

  final List<(String sectionKey, int posInSection, int totalInSection)>
      _byGlobal;
  final List<String> _sectionKeysInOrder;
  final Map<String, List<int>> _indicesBySection;

  bool get isEmpty => _byGlobal.isEmpty;

  int get sectionCount => _sectionKeysInOrder.length;

  String sectionLabelAt(int sectionIndex) {
    if (sectionIndex < 0 || sectionIndex >= _sectionKeysInOrder.length) {
      return '';
    }
    return sectionDisplayName(_sectionKeysInOrder[sectionIndex]);
  }

  int positionCountForSection(int sectionIndex) {
    if (sectionIndex < 0 || sectionIndex >= _sectionKeysInOrder.length) {
      return 0;
    }
    return _indicesBySection[_sectionKeysInOrder[sectionIndex]]?.length ?? 0;
  }

  /// 0-based position within section → global sentence index.
  int? globalIndexFor(int sectionIndex, int positionIndex) {
    if (sectionIndex < 0 || sectionIndex >= _sectionKeysInOrder.length) {
      return null;
    }
    final indices = _indicesBySection[_sectionKeysInOrder[sectionIndex]]!;
    if (positionIndex < 0 || positionIndex >= indices.length) return null;
    return indices[positionIndex];
  }

  (int sectionIndex, int positionIndex) selectionForGlobal(int globalIndex) {
    if (globalIndex < 0 || globalIndex >= _byGlobal.length) {
      return (0, 0);
    }
    final (key, pos, _) = _byGlobal[globalIndex];
    final sectionIndex = _sectionKeysInOrder.indexOf(key);
    return (sectionIndex < 0 ? 0 : sectionIndex, pos > 0 ? pos - 1 : 0);
  }

  SectionHeaderParts headerPartsFor(int globalIndex) {
    if (globalIndex < 0 || globalIndex >= _byGlobal.length) {
      return const SectionHeaderParts(
        sectionName: '',
        position: 0,
        total: 0,
      );
    }
    final (key, pos, total) = _byGlobal[globalIndex];
    return SectionHeaderParts(
      sectionName: sectionDisplayName(key),
      position: pos,
      total: total,
    );
  }

  String labelFor(int globalIndex, {int totalSentences = 0}) {
    final parts = headerPartsFor(globalIndex);
    if (parts.total == 0) {
      return totalSentences == 0
          ? 'no sentences'
          : 'sentence ${globalIndex + 1} / $totalSentences';
    }
    if (parts.sectionName.isEmpty) {
      return 'sentence ${parts.position} / ${parts.total}';
    }
    return '${parts.sectionName} ${parts.position} / ${parts.total}';
  }

  /// Internal section key (e.g. introduction) for bookmark stable keys.
  String sectionKeyAt(int sectionIndex) {
    if (sectionIndex < 0 || sectionIndex >= _sectionKeysInOrder.length) {
      return '';
    }
    return _sectionKeysInOrder[sectionIndex];
  }

  /// Bookmark key `{sectionKey}:{position}` — position is 1-based within section.
  String? sentenceBookmarkKeyForGlobal(int globalIndex) {
    if (globalIndex < 0 || globalIndex >= _byGlobal.length) return null;
    final (key, pos, _) = _byGlobal[globalIndex];
    if (key.isEmpty || pos < 1) return null;
    return '$key:$pos';
  }

  String? sentenceBookmarkKeyForSelection(int sectionIndex, int positionIndex) {
    final key = sectionKeyAt(sectionIndex);
    if (key.isEmpty) return null;
    final pos = positionIndex + 1;
    final total = positionCountForSection(sectionIndex);
    if (pos < 1 || pos > total) return null;
    return '$key:$pos';
  }

  bool isValidSentenceBookmarkKey(String bookmarkKey) {
    final sep = bookmarkKey.lastIndexOf(':');
    if (sep <= 0) return false;
    final key = bookmarkKey.substring(0, sep);
    final pos = int.tryParse(bookmarkKey.substring(sep + 1));
    if (pos == null || pos < 1) return false;
    final sectionIndex = _sectionKeysInOrder.indexOf(key);
    if (sectionIndex < 0) return false;
    return pos <= positionCountForSection(sectionIndex);
  }

  int sectionBookmarkCount(Set<String> keys, int sectionIndex) {
    final sectionKey = sectionKeyAt(sectionIndex);
    if (sectionKey.isEmpty) return 0;
    final prefix = '$sectionKey:';
    return keys.where((k) => k.startsWith(prefix)).length;
  }
}

String _sectionKey(String? section) {
  final s = (section ?? '').trim().toLowerCase();
  return s.isEmpty ? 'body' : s;
}

/// Header split for figure/table carousel.
class FigureHeaderParts {
  const FigureHeaderParts({
    required this.kindLabel,
    required this.numberLabel,
    required this.totalLabel,
  });

  final String kindLabel;
  final String numberLabel;
  final String totalLabel;

  String get rightLabel =>
      totalLabel.isNotEmpty ? '$numberLabel / $totalLabel' : '— / —';
}

/// Carousel index ↔ paper figure/table slot number.
class FigureNavIndex {
  FigureNavIndex._({
    required List<String> labels,
    required List<String> kindsInOrder,
    required Map<String, List<int>> numbersByKind,
    required Map<String, Map<int, int>> carouselByKindNumber,
  })  : _labels = labels,
        _kindsInOrder = kindsInOrder,
        _numbersByKind = numbersByKind,
        _carouselByKindNumber = carouselByKindNumber;

  factory FigureNavIndex.fromFigures(List<FigureView> figures) {
    final figNumbers = <int>[];
    final tableNumbers = <int>[];
    final figSNumbers = <int>[];
    final tableSNumbers = <int>[];
    final figCarousel = <int, int>{};
    final tableCarousel = <int, int>{};
    final figSCarousel = <int, int>{};
    final tableSCarousel = <int, int>{};
    final labels = List<String>.filled(figures.length, '');

    for (var i = 0; i < figures.length; i++) {
      final slot = _slotKindNumber(figures[i]);
      if (slot == null) {
        labels[i] = 'figure ${i + 1} / ${figures.length}';
        continue;
      }
      final (kind, num) = slot;
      switch (kind) {
        case 'table':
          tableNumbers.add(num);
          tableCarousel[num] = i;
        case 'table_s':
          tableSNumbers.add(num);
          tableSCarousel[num] = i;
        case 'figure_s':
          figSNumbers.add(num);
          figSCarousel[num] = i;
        default:
          figNumbers.add(num);
          figCarousel[num] = i;
      }
    }

    figNumbers.sort();
    tableNumbers.sort();
    figSNumbers.sort();
    tableSNumbers.sort();
    final kindsInOrder = <String>[];
    final numbersByKind = <String, List<int>>{};
    final carouselByKindNumber = <String, Map<int, int>>{};
    void addKind(String kind, List<int> nums, Map<int, int> carousel) {
      if (nums.isEmpty) return;
      kindsInOrder.add(kind);
      numbersByKind[kind] = nums;
      carouselByKindNumber[kind] = carousel;
    }

    addKind('figure', figNumbers, figCarousel);
    addKind('table', tableNumbers, tableCarousel);
    addKind('figure_s', figSNumbers, figSCarousel);
    addKind('table_s', tableSNumbers, tableSCarousel);

    int maxOf(List<int> nums) =>
        nums.isEmpty ? 0 : nums.reduce((a, b) => a > b ? a : b);
    final figTotal = maxOf(figNumbers);
    final tableTotal = maxOf(tableNumbers);
    final figSTotal = maxOf(figSNumbers);
    final tableSTotal = maxOf(tableSNumbers);

    String numLabel(String kind, int num) {
      if (kind == 'figure_s' || kind == 'table_s') return 'S$num';
      return '$num';
    }

    for (var i = 0; i < figures.length; i++) {
      final slot = _slotKindNumber(figures[i]);
      if (slot == null) continue;
      final (kind, num) = slot;
      switch (kind) {
        case 'table':
          final total = tableTotal > 0 ? tableTotal : tableNumbers.length;
          labels[i] = 'table ${numLabel(kind, num)} / $total';
        case 'table_s':
          final total = tableSTotal > 0 ? tableSTotal : tableSNumbers.length;
          labels[i] = 'table ${numLabel(kind, num)} / ${numLabel(kind, total)}';
        case 'figure_s':
          final total = figSTotal > 0 ? figSTotal : figSNumbers.length;
          labels[i] = 'figure ${numLabel(kind, num)} / ${numLabel(kind, total)}';
        default:
          final total = figTotal > 0 ? figTotal : figNumbers.length;
          labels[i] = 'figure ${numLabel(kind, num)} / $total';
      }
    }

    return FigureNavIndex._(
      labels: labels,
      kindsInOrder: kindsInOrder,
      numbersByKind: numbersByKind,
      carouselByKindNumber: carouselByKindNumber,
    );
  }

  final List<String> _labels;
  final List<String> _kindsInOrder;
  final Map<String, List<int>> _numbersByKind;
  final Map<String, Map<int, int>> _carouselByKindNumber;

  bool get isEmpty => _labels.isEmpty;

  bool get hasPicker => _kindsInOrder.isNotEmpty;

  int get kindCount => _kindsInOrder.length;

  String kindLabelAt(int kindIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return '';
    switch (_kindsInOrder[kindIndex]) {
      case 'table':
      case 'table_s':
        return 'Table';
      case 'figure_s':
        return 'Figure S';
      default:
        return 'Figure';
    }
  }

  String numberLabelAt(int kindIndex, int numberIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return '1';
    final kind = _kindsInOrder[kindIndex];
    final nums = _numbersByKind[kind] ?? [];
    if (numberIndex < 0 || numberIndex >= nums.length) {
      final n = nums.isNotEmpty ? nums.first : 1;
      return _displayNumber(kind, n);
    }
    return _displayNumber(kind, nums[numberIndex]);
  }

  String totalLabelForKind(int kindIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return '';
    final kind = _kindsInOrder[kindIndex];
    final nums = _numbersByKind[kind] ?? [];
    if (nums.isEmpty) return '';
    final total = nums.reduce((a, b) => a > b ? a : b);
    return _displayNumber(kind, total);
  }

  static String _displayNumber(String kind, int num) {
    if (kind == 'figure_s' || kind == 'table_s') return 'S$num';
    return '$num';
  }

  int numberCountForKind(int kindIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return 0;
    return _numbersByKind[_kindsInOrder[kindIndex]]?.length ?? 0;
  }

  int numberAt(int kindIndex, int numberIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return 1;
    final nums = _numbersByKind[_kindsInOrder[kindIndex]] ?? [];
    if (numberIndex < 0 || numberIndex >= nums.length) {
      return nums.isNotEmpty ? nums.first : 1;
    }
    return nums[numberIndex];
  }

  int totalNumberForKind(int kindIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return 0;
    final nums = _numbersByKind[_kindsInOrder[kindIndex]] ?? [];
    if (nums.isEmpty) return 0;
    return nums.reduce((a, b) => a > b ? a : b);
  }

  int? carouselIndexFor(int kindIndex, int numberIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return null;
    final kind = _kindsInOrder[kindIndex];
    final nums = _numbersByKind[kind] ?? [];
    if (numberIndex < 0 || numberIndex >= nums.length) return null;
    return _carouselByKindNumber[kind]?[nums[numberIndex]];
  }

  (int kindIndex, int numberIndex) selectionForCarousel(int carouselIndex) {
    if (_kindsInOrder.isEmpty) return (0, 0);
    final slot = carouselIndex >= 0 && carouselIndex < _labels.length
        ? _slotFromCarousel(carouselIndex)
        : null;
    if (slot == null) return (0, 0);
    final (kind, num) = slot;
    final kindIndex = _kindsInOrder.indexOf(kind);
    if (kindIndex < 0) return (0, 0);
    final nums = _numbersByKind[kind] ?? [];
    final numberIndex = nums.indexOf(num);
    return (kindIndex, numberIndex < 0 ? 0 : numberIndex);
  }

  (String kind, int number)? _slotFromCarousel(int carouselIndex) {
    // Re-parse from label cache path — use stored maps in reverse.
    for (final kind in _kindsInOrder) {
      for (final entry in _carouselByKindNumber[kind]!.entries) {
        if (entry.value == carouselIndex) {
          return (kind, entry.key);
        }
      }
    }
    return null;
  }

  FigureHeaderParts headerPartsFor(int carouselIndex, {int totalFigures = 0}) {
    if (carouselIndex < 0 || carouselIndex >= _labels.length) {
      return const FigureHeaderParts(
        kindLabel: '',
        numberLabel: '',
        totalLabel: '',
      );
    }
    final slot = _slotFromCarousel(carouselIndex);
    if (slot == null) {
      return FigureHeaderParts(
        kindLabel: 'Figure',
        numberLabel: '${carouselIndex + 1}',
        totalLabel: totalFigures > 0 ? '$totalFigures' : '',
      );
    }
    final (kind, num) = slot;
    final nums = _numbersByKind[kind] ?? [];
    final total = nums.isEmpty
        ? 0
        : nums.reduce((a, b) => a > b ? a : b);
    final kindLabel = kind == 'table' || kind == 'table_s'
        ? 'Table'
        : (kind == 'figure_s' ? 'Figure S' : 'Figure');
    return FigureHeaderParts(
      kindLabel: kindLabel,
      numberLabel: _displayNumber(kind, num),
      totalLabel: total > 0 ? _displayNumber(kind, total) : '${nums.length}',
    );
  }

  String labelFor(int carouselIndex, {int totalFigures = 0}) {
    if (carouselIndex < 0 || carouselIndex >= _labels.length) {
      return totalFigures == 0 ? 'no figures' : 'figure — / $totalFigures';
    }
    final label = _labels[carouselIndex];
    if (label.isNotEmpty) return label;
    return totalFigures == 0
        ? 'no figures'
        : 'figure ${carouselIndex + 1} / $totalFigures';
  }

  String kindKeyAt(int kindIndex) {
    if (kindIndex < 0 || kindIndex >= _kindsInOrder.length) return '';
    return _kindsInOrder[kindIndex];
  }

  /// Bookmark key `{kind}:{number}` — e.g. figure:1, figure_s:2.
  String? figureBookmarkKeyForCarousel(int carouselIndex) {
    final slot = _slotFromCarousel(carouselIndex);
    if (slot == null) return null;
    final (kind, num) = slot;
    return '$kind:$num';
  }

  String? figureBookmarkKeyForSelection(int kindIndex, int numberIndex) {
    final kind = kindKeyAt(kindIndex);
    if (kind.isEmpty) return null;
    final num = numberAt(kindIndex, numberIndex);
    return '$kind:$num';
  }

  bool isValidFigureBookmarkKey(String bookmarkKey) {
    final sep = bookmarkKey.indexOf(':');
    if (sep <= 0) return false;
    final kind = bookmarkKey.substring(0, sep);
    final num = int.tryParse(bookmarkKey.substring(sep + 1));
    if (num == null || num < 1) return false;
    final kindIndex = _kindsInOrder.indexOf(kind);
    if (kindIndex < 0) return false;
    final nums = _numbersByKind[kind] ?? [];
    return nums.contains(num);
  }

  int kindBookmarkCount(Set<String> keys, int kindIndex) {
    final kind = kindKeyAt(kindIndex);
    if (kind.isEmpty) return 0;
    final prefix = '$kind:';
    return keys.where((k) => k.startsWith(prefix)).length;
  }
}

(String kind, int number)? _slotKindNumber(FigureView fig) {
  final key = fig.slotKey.trim().toLowerCase();
  if (key.isNotEmpty) {
    final si = RegExp(r'^(fig|table):s(\d+)$').firstMatch(key);
    if (si != null) {
      final k = si.group(1)! == 'table' ? 'table_s' : 'figure_s';
      return (k, int.parse(si.group(2)!));
    }
    final m = RegExp(r'^(fig|figure|table):(\d+)$').firstMatch(key);
    if (m != null) {
      final kind = m.group(1)! == 'table' ? 'table' : 'figure';
      return (kind, int.parse(m.group(2)!));
    }
  }
  final capKey = captionFigKey(fig.caption);
  if (capKey == null) return null;
  if (capKey.startsWith('table:s')) {
    return ('table_s', int.parse(capKey.split(':').last.substring(1)));
  }
  if (capKey.startsWith('fig:s') || capKey.startsWith('scheme:s')) {
    return ('figure_s', int.parse(capKey.split(':').last.substring(1)));
  }
  if (capKey.startsWith('table:')) {
    return ('table', int.parse(capKey.split(':').last));
  }
  if (capKey.startsWith('fig:') || capKey.startsWith('scheme:')) {
    return ('figure', int.parse(capKey.split(':').last));
  }
  return null;
}
