/// design/492 — attach documents behind a paper: confirm, pick a paper, pick the head.
library;

import 'package:flutter/material.dart';

import '../api/doc_parts.dart';
import '../api/paper_models.dart';
import '../pdf/normalize_pairing_key.dart';

const String kAttachMergedPartNote = '합친 문서는 다른 문서 뒤에 붙일 수 없어요.';

/// One line per part, in the order they will be read.
String attachPartLines(List<PaperEntry> parts) => [
      for (final p in orderParts(parts))
        '· ${kPartSectionNames[partSectionFor(p)]} — ${p.shownTitle}',
    ].join('\n');

/// The merge button's hover text: what joins this paper.
String attachTooltip(List<PaperEntry> parts) {
  final names = <String>[];
  for (final p in orderParts(parts)) {
    final n = kPartSectionNames[partSectionFor(p)]!;
    if (!names.contains(n)) names.add(n);
  }
  return '${parts.length + 1}개 합치기: 논문 · ${names.join(' · ')}';
}

Future<bool> confirmAttach(
  BuildContext context, {
  required PaperEntry main,
  required List<PaperEntry> parts,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(parts.length == 1 ? '문서 붙이기' : '${parts.length + 1}개 합치기'),
      content: SingleChildScrollView(
        child: Text(
          '「${main.shownTitle}」 뒤에 이어 붙여요.\n\n'
          '${attachPartLines(parts)}\n\n'
          '붙인 문서는 목록에서 숨겨지고, 읽기 화면에서 이어서 나와요.',
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('취소'),
        ),
        FilledButton(
          key: const ValueKey('attach_confirm'),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('합치기'),
        ),
      ],
    ),
  );
  return ok == true;
}

/// Papers [part] can go behind: the same file number first, then the same
/// title, then the rest in library order.
List<PaperEntry> attachTargetsFor(PaperEntry part, List<PaperEntry> papers) {
  final fk = fileArticleKey(part.sourceName);
  final tk = normalizePairingKey(part.title);
  int rank(PaperEntry e) {
    if (fk.isNotEmpty && fileArticleKey(e.sourceName) == fk) return 0;
    if (tk.isNotEmpty && normalizePairingKey(e.title) == tk) return 1;
    return 2;
  }

  final out = [
    for (var i = 0; i < papers.length; i++)
      if (papers[i].id != part.id &&
          papers[i].docRole.trim().toLowerCase() != 'supplementary')
        (i, papers[i]),
  ];
  out.sort((a, b) {
    final r = rank(a.$2).compareTo(rank(b.$2));
    return r != 0 ? r : a.$1.compareTo(b.$1);
  });
  return [for (final e in out) e.$2];
}

Future<String?> pickAttachTarget(
  BuildContext context, {
  required PaperEntry part,
  required List<PaperEntry> targets,
}) {
  return showModalBottomSheet<String>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(ctx).height * 0.7,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
              child: Text(
                '「${part.shownTitle}」을 어느 문서 뒤에 붙일까요?',
                style: Theme.of(ctx).textTheme.titleSmall,
              ),
            ),
            if (targets.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text('붙일 수 있는 문서가 없어요.'),
              ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final t in targets)
                    ListTile(
                      key: ValueKey('attach_target_${t.id}'),
                      title: Text(t.shownTitle),
                      subtitle: t.shownTag.isEmpty ? null : Text(t.shownTag),
                      onTap: () => Navigator.pop(ctx, t.id),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// Which of the selected documents comes first; the paper is suggested.
Future<String?> pickMergeHead(
  BuildContext context, {
  required List<PaperEntry> selected,
}) {
  final heads = [
    for (final e in selected)
      if (e.docRole.trim().toLowerCase() != 'supplementary') e,
  ];
  if (heads.isEmpty) return Future.value(null);
  var pick = heads
      .firstWhere(
        (e) => e.docRole.trim().toLowerCase() == 'merged',
        orElse: () => heads.firstWhere(
          (e) => e.effectiveKind == 'paper',
          orElse: () => heads.first,
        ),
      )
      .id;
  return showDialog<String>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: const Text('맨 앞에 올 문서'),
        content: SingleChildScrollView(
          child: RadioGroup<String>(
            groupValue: pick,
            onChanged: (v) => setState(() => pick = v ?? pick),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final e in heads)
                  RadioListTile<String>(
                    key: ValueKey('merge_head_${e.id}'),
                    value: e.id,
                    title: Text(e.shownTitle),
                    subtitle: e.shownTag.isEmpty ? null : Text(e.shownTag),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소'),
          ),
          FilledButton(
            key: const ValueKey('merge_head_next'),
            onPressed: () => Navigator.pop(ctx, pick),
            child: const Text('다음'),
          ),
        ],
      ),
    ),
  );
}
