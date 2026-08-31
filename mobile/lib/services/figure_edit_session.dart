/// In-memory figure layout edit session (design/163).
library;

import 'dart:typed_data';

import 'figure_edit_geometry.dart';

class FigureEditSlotState {
  FigureEditSlotState({
    required this.key,
    required this.kind,
    this.bodyBoxIds = const [],
    this.captionBoxIds = const [],
    this.bodyUnion,
    this.captionUnion,
    this.previewPng,
    this.captionText = '',
    this.status = 'empty',
  });

  final String key;
  final String kind;
  List<String> bodyBoxIds;
  List<String> captionBoxIds;
  NormRect? bodyUnion;
  NormRect? captionUnion;
  Uint8List? previewPng;
  String captionText;
  String status;

  bool get isTable => kind == 'table';

  Map<String, dynamic> toJson() => {
        'key': key,
        'kind': kind,
        'status': status,
        'body_box_ids': bodyBoxIds,
        'caption_box_ids': captionBoxIds,
        'caption_text': captionText,
      };
}

class FigureEditSession {
  FigureEditSession({
    required this.cacheId,
    required Map<String, dynamic> layoutMap,
    required List<Map<String, dynamic>> slots,
  })  : layoutMap = Map<String, dynamic>.from(layoutMap),
        slotStates = slots
            .map(
              (s) => FigureEditSlotState(
                key: '${s['key'] ?? ''}',
                kind: '${s['kind'] ?? 'fig'}',
                bodyBoxIds: [
                  for (final x in (s['body_box_ids'] as List?) ?? [])
                    if ('$x'.trim().isNotEmpty) '$x',
                ],
                captionBoxIds: [
                  for (final x in (s['caption_box_ids'] as List?) ?? [])
                    if ('$x'.trim().isNotEmpty) '$x',
                ],
                captionText: '${s['caption_text'] ?? ''}',
                status: '${s['status'] ?? 'empty'}',
              ),
            )
            .toList() {
    for (final s in slotStates) {
      if (s.bodyBoxIds.isEmpty) {
        final legacy = slots
            .where((r) => '${r['key']}' == s.key)
            .map((r) => '${r['body_box_id'] ?? ''}')
            .firstWhere((x) => x.isNotEmpty, orElse: () => '');
        if (legacy.isNotEmpty) s.bodyBoxIds = [legacy];
      }
      if (s.captionBoxIds.isEmpty) {
        final legacy = slots
            .where((r) => '${r['key']}' == s.key)
            .map((r) => '${r['caption_box_id'] ?? ''}')
            .firstWhere((x) => x.isNotEmpty, orElse: () => '');
        if (legacy.isNotEmpty) s.captionBoxIds = [legacy];
      }
    }
  }

  final String cacheId;
  Map<String, dynamic> layoutMap;
  final List<FigureEditSlotState> slotStates;
  bool dirty = false;
  int manualBoxSeq = 0;

  FigureEditSlotState? slotByKey(String key) {
    final want = key.trim().toLowerCase();
    for (final s in slotStates) {
      if (s.key.toLowerCase() == want) return s;
    }
    return null;
  }

  List<Map<String, dynamic>> get boxes {
    final raw = layoutMap['boxes'];
    if (raw is! List) return [];
    return raw.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  void addManualBox({
    required int pageIndex,
    required NormRect rect,
    String kind = 'figure_body',
  }) {
    manualBoxSeq += 1;
    final id = 'user-crop-$manualBoxSeq';
    final pw = pageWidth(pageIndex);
    final ph = pageHeight(pageIndex);
    boxes.add({
      'id': id,
      'page_index': pageIndex,
      'kind': kind,
      'source': 'user',
      'rect': {
        'x0': rect.left * pw,
        'y0': rect.top * ph,
        'x1': rect.right * pw,
        'y1': rect.bottom * ph,
      },
      'text': '',
    });
    layoutMap['boxes'] = boxes;
    dirty = true;
  }

  int pageWidth(int pageIndex) {
    final pages = layoutMap['pages'];
    if (pages is List && pageIndex < pages.length && pages[pageIndex] is Map) {
      return ((pages[pageIndex] as Map)['width_pt'] as num?)?.toInt() ?? 612;
    }
    return 612;
  }

  int pageHeight(int pageIndex) {
    final pages = layoutMap['pages'];
    if (pages is List && pageIndex < pages.length && pages[pageIndex] is Map) {
      return ((pages[pageIndex] as Map)['height_pt'] as num?)?.toInt() ?? 792;
    }
    return 792;
  }

  Map<String, dynamic> slotPlanJson() => {
        'version': 1,
        'slots': slotStates.map((s) => s.toJson()).toList(),
      };
}
