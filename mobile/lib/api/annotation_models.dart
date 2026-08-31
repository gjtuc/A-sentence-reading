/// Reader annotation store — stable keys + merge (GCS sync, design/166).
library;

import 'package:flutter/material.dart';

const kAnnotationsStoreVersion = 1;
const kAnnotationsPrefsKey = 'asr.annotations.v1';

const annotationColors = ['yellow', 'green', 'blue', 'pink'];

/// One annotation event (latest [at] per [id] wins on merge; [deleted] tombstone).
class AnnotationEvent {
  const AnnotationEvent({
    required this.id,
    required this.at,
    required this.kind,
    this.deleted = false,
    this.color = 'yellow',
    this.style = 'solid',
    this.motivation = 'highlighting',
    this.note = '',
    this.sentenceId = '',
    this.charRange,
    this.selector,
    this.status = '',
    this.paths = const [],
  });

  final String id;
  final String at;
  final bool deleted;
  final String kind;
  final String color;
  final String style;
  final String motivation;
  final String note;
  final String sentenceId;
  final List<int>? charRange;
  final Map<String, dynamic>? selector;
  final String status;
  final List<Map<String, dynamic>> paths;

  bool get isActive => !deleted;

  Map<String, dynamic> toJson() => {
        'id': id,
        'at': at,
        if (deleted) 'deleted': true,
        'kind': kind,
        if (color.isNotEmpty) 'color': color,
        if (style.isNotEmpty) 'style': style,
        if (motivation.isNotEmpty) 'motivation': motivation,
        if (note.isNotEmpty) 'note': note,
        if (sentenceId.isNotEmpty) 'sentence_id': sentenceId,
        if (charRange != null && charRange!.length == 2) 'char_range': charRange,
        if (selector != null && selector!.isNotEmpty) 'selector': selector,
        if (status.isNotEmpty) 'status': status,
        if (paths.isNotEmpty) 'paths': paths,
      };

  static AnnotationEvent? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final id = '${raw['id'] ?? ''}'.trim();
    final at = raw['at'];
    if (id.isEmpty || at is! String || at.trim().isEmpty) return null;
    List<int>? charRange;
    final cr = raw['char_range'];
    if (cr is List && cr.length == 2) {
      final a = cr[0];
      final b = cr[1];
      if (a is int && b is int) charRange = [a, b];
    }
    final pathsRaw = raw['paths'];
    final paths = <Map<String, dynamic>>[];
    if (pathsRaw is List) {
      for (final p in pathsRaw) {
        if (p is Map) paths.add(Map<String, dynamic>.from(p));
      }
    }
    Map<String, dynamic>? selector;
    final sel = raw['selector'];
    if (sel is Map) selector = Map<String, dynamic>.from(sel);
    return AnnotationEvent(
      id: id,
      at: at,
      deleted: raw['deleted'] == true,
      kind: '${raw['kind'] ?? 'highlight'}',
      color: '${raw['color'] ?? 'yellow'}',
      style: '${raw['style'] ?? 'solid'}',
      motivation: '${raw['motivation'] ?? 'highlighting'}',
      note: '${raw['note'] ?? ''}',
      sentenceId: '${raw['sentence_id'] ?? ''}',
      charRange: charRange,
      selector: selector,
      status: '${raw['status'] ?? ''}',
      paths: paths,
    );
  }

  AnnotationEvent copyWith({
    String? at,
    bool? deleted,
    String? color,
    String? note,
    String? sentenceId,
    String? status,
    List<Map<String, dynamic>>? paths,
  }) {
    return AnnotationEvent(
      id: id,
      at: at ?? this.at,
      deleted: deleted ?? this.deleted,
      kind: kind,
      color: color ?? this.color,
      style: style,
      motivation: motivation,
      note: note ?? this.note,
      sentenceId: sentenceId ?? this.sentenceId,
      charRange: charRange,
      selector: selector,
      status: status ?? this.status,
      paths: paths ?? this.paths,
    );
  }
}

/// Per-paper annotation maps keyed by `{section}:{position}` or `figure:{n}`.
class PaperAnnotations {
  const PaperAnnotations({
    this.sentences = const {},
    this.figures = const {},
  });

  final Map<String, List<AnnotationEvent>> sentences;
  final Map<String, List<AnnotationEvent>> figures;

  List<AnnotationEvent> activeEventsForSentenceKey(String key) {
    return (sentences[key] ?? const [])
        .where((e) => e.isActive)
        .toList(growable: false);
  }

  List<AnnotationEvent> activeEventsForFigureKey(String key) {
    return (figures[key] ?? const [])
        .where((e) => e.isActive)
        .toList(growable: false);
  }

  int get totalActiveCount {
    var n = 0;
    for (final list in sentences.values) {
      n += list.where((e) => e.isActive).length;
    }
    for (final list in figures.values) {
      n += list.where((e) => e.isActive).length;
    }
    return n;
  }

  PaperAnnotations copyWith({
    Map<String, List<AnnotationEvent>>? sentences,
    Map<String, List<AnnotationEvent>>? figures,
  }) {
    return PaperAnnotations(
      sentences: sentences ?? this.sentences,
      figures: figures ?? this.figures,
    );
  }

  Map<String, dynamic> toJson() => {
        'sentences': {
          for (final e in sentences.entries)
            e.key: e.value.map((v) => v.toJson()).toList(),
        },
        'figures': {
          for (final e in figures.entries)
            e.key: e.value.map((v) => v.toJson()).toList(),
        },
      };

  static PaperAnnotations fromJson(Object? raw) {
    if (raw is! Map) return const PaperAnnotations();
    return PaperAnnotations(
      sentences: _parseMap(raw['sentences']),
      figures: _parseMap(raw['figures']),
    );
  }

  static Map<String, List<AnnotationEvent>> _parseMap(Object? raw) {
    if (raw is! Map) return {};
    final out = <String, List<AnnotationEvent>>{};
    for (final entry in raw.entries) {
      final key = entry.key.toString().trim();
      if (key.isEmpty) continue;
      final list = entry.value;
      if (list is! List) continue;
      final events = <AnnotationEvent>[];
      for (final item in list) {
        final ev = AnnotationEvent.fromJson(item);
        if (ev != null) events.add(ev);
      }
      if (events.isNotEmpty) out[key] = events;
    }
    return out;
  }
}

class AnnotationsStore {
  const AnnotationsStore({
    this.version = kAnnotationsStoreVersion,
    this.papers = const {},
  });

  final int version;
  final Map<String, PaperAnnotations> papers;

  AnnotationsStore copyWith({Map<String, PaperAnnotations>? papers}) {
    return AnnotationsStore(version: version, papers: papers ?? this.papers);
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'papers': {
          for (final e in papers.entries) e.key: e.value.toJson(),
        },
      };

  static AnnotationsStore empty() => const AnnotationsStore();

  static AnnotationsStore fromJson(Object? raw) {
    if (raw is! Map) return AnnotationsStore.empty();
    final ver = raw['version'];
    if (ver is! int || ver != kAnnotationsStoreVersion) {
      return AnnotationsStore.empty();
    }
    final papersRaw = raw['papers'];
    if (papersRaw is! Map) return const AnnotationsStore();
    final papers = <String, PaperAnnotations>{};
    for (final entry in papersRaw.entries) {
      final key = entry.key.toString().trim();
      if (key.isEmpty) continue;
      papers[key] = PaperAnnotations.fromJson(entry.value);
    }
    return AnnotationsStore(papers: papers);
  }
}

String annotationPaperKey(String cacheId) => 'cache:${cacheId.trim()}';

String annotationsPrefsKey(String? uid) {
  final u = (uid ?? '').trim().replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '');
  if (u.isEmpty) return kAnnotationsPrefsKey;
  final safe = u.length > 128 ? u.substring(0, 128) : u;
  return '$kAnnotationsPrefsKey.u.$safe';
}

AnnotationEvent annotationEventNow({
  required String id,
  String kind = 'highlight',
  bool deleted = false,
  String color = 'yellow',
  String note = '',
  String sentenceId = '',
  List<int>? charRange,
  Map<String, dynamic>? selector,
  String status = '',
  List<Map<String, dynamic>> paths = const [],
}) {
  return AnnotationEvent(
    id: id,
    at: DateTime.now().toUtc().toIso8601String(),
    deleted: deleted,
    kind: kind,
    color: color,
    note: note,
    sentenceId: sentenceId,
    charRange: charRange,
    selector: selector,
    status: status,
    paths: paths,
  );
}

List<AnnotationEvent> mergeAnnotationEvents(
  List<AnnotationEvent> a,
  List<AnnotationEvent> b,
) {
  final byId = <String, AnnotationEvent>{};
  for (final ev in [...a, ...b]) {
    final prev = byId[ev.id];
    if (prev == null || ev.at.compareTo(prev.at) >= 0) {
      byId[ev.id] = ev;
    }
  }
  return byId.values.toList();
}

Map<String, List<AnnotationEvent>> mergeAnnotationKeyMaps(
  Map<String, List<AnnotationEvent>> a,
  Map<String, List<AnnotationEvent>> b,
) {
  final keys = {...a.keys, ...b.keys};
  final out = <String, List<AnnotationEvent>>{};
  for (final key in keys) {
    final merged = mergeAnnotationEvents(a[key] ?? const [], b[key] ?? const [])
        .where((e) => e.isActive)
        .toList();
    if (merged.isNotEmpty) out[key] = merged;
  }
  return out;
}

PaperAnnotations mergePaperAnnotations(PaperAnnotations a, PaperAnnotations b) {
  return PaperAnnotations(
    sentences: mergeAnnotationKeyMaps(a.sentences, b.sentences),
    figures: mergeAnnotationKeyMaps(a.figures, b.figures),
  );
}

AnnotationsStore mergeAnnotationsStores(AnnotationsStore a, AnnotationsStore b) {
  final keys = {...a.papers.keys, ...b.papers.keys};
  final papers = <String, PaperAnnotations>{};
  for (final key in keys) {
    final pa = a.papers[key] ?? const PaperAnnotations();
    final pb = b.papers[key] ?? const PaperAnnotations();
    final merged = mergePaperAnnotations(pa, pb);
    if (merged.sentences.isNotEmpty || merged.figures.isNotEmpty) {
      papers[key] = merged;
    }
  }
  return AnnotationsStore(papers: papers);
}

PaperAnnotations compactPaperAnnotations(PaperAnnotations paper) => paper;

AnnotationsStore compactAnnotationsStore(AnnotationsStore store) {
  final papers = <String, PaperAnnotations>{};
  for (final entry in store.papers.entries) {
    if (entry.value.sentences.isNotEmpty || entry.value.figures.isNotEmpty) {
      papers[entry.key] = entry.value;
    }
  }
  return AnnotationsStore(papers: papers);
}

Color annotationColorValue(String name) {
  switch (name) {
    case 'green':
      return const Color(0xFFC8E6C9);
    case 'blue':
      return const Color(0xFFBBDEFB);
    case 'pink':
      return const Color(0xFFF8BBD0);
    case 'yellow':
    default:
      return const Color(0xFFFFF59D);
  }
}

String newAnnotationId() {
  final ts = DateTime.now().toUtc().microsecondsSinceEpoch;
  final r = ts.hashCode.abs();
  return 'ann-$ts-$r';
}
