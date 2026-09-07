import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/ai_ask_prompt_models.dart';
import '../api/ai_ask_prompt_store.dart';
import '../api/annotation_models.dart';

/// Bottom sheet: paint colors + memo + AI ask (design/166 · 182).
Future<AnnotationToolbarResult?> showAnnotationToolbarSheet({
  required BuildContext context,
  List<AnnotationEvent> existing = const [],
  bool canAnnotate = true,
  AiAskPromptStore? promptStore,
}) {
  return showModalBottomSheet<AnnotationToolbarResult>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) {
      return _AnnotationToolbarBody(
        existing: existing,
        canAnnotate: canAnnotate,
        promptStore: promptStore ?? PrefsAiAskPromptStore(),
      );
    },
  );
}

enum AnnotationSheetAction {
  armPaint,
  saveMeta,
  deleteAll,
  askAi,
}

class AnnotationToolbarResult {
  const AnnotationToolbarResult({
    required this.action,
    this.color = 'yellow',
    this.note = '',
    this.existingId,
    this.promptBody,
  });

  final AnnotationSheetAction action;
  final String color;
  final String note;
  final String? existingId;
  final String? promptBody;

  /// Back-compat for callers that only checked [delete].
  bool get delete => action == AnnotationSheetAction.deleteAll;
}

class _AnnotationToolbarBody extends StatefulWidget {
  const _AnnotationToolbarBody({
    this.existing = const [],
    required this.canAnnotate,
    required this.promptStore,
  });

  final List<AnnotationEvent> existing;
  final bool canAnnotate;
  final AiAskPromptStore promptStore;

  @override
  State<_AnnotationToolbarBody> createState() => _AnnotationToolbarBodyState();
}

class _AnnotationToolbarBodyState extends State<_AnnotationToolbarBody> {
  late String _color;
  late final TextEditingController _noteCtrl;
  String? _existingId;
  List<AiAskPrompt> _prompts = const [];
  bool _loadingPrompts = true;

  @override
  void initState() {
    super.initState();
    final first = widget.existing.isNotEmpty ? widget.existing.first : null;
    _color = first?.color ?? 'yellow';
    _existingId = first?.id;
    _noteCtrl = TextEditingController(text: first?.note ?? '');
    _loadPrompts();
  }

  Future<void> _loadPrompts() async {
    final list = await loadAiAskPromptsEnsuringSeed(widget.promptStore);
    if (!mounted) return;
    setState(() {
      _prompts = list;
      _loadingPrompts = false;
    });
  }

  @override
  void dispose() {
    _noteCtrl.dispose();
    super.dispose();
  }

  void _needLogin() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('주석을 쓰려면 로그인해 주세요.')),
    );
  }

  Future<void> _managePrompts() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) => _PromptManageSheet(
        store: widget.promptStore,
        initial: _prompts,
        onChanged: (next) {
          if (mounted) setState(() => _prompts = next);
        },
      ),
    );
    await _loadPrompts();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        16,
        8,
        16,
        16 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('하이라이트', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(
              widget.canAnnotate
                  ? '색을 고른 뒤 문장에서 칠할 부분을 드래그하세요'
                  : '하이라이트는 로그인 후 사용할 수 있습니다',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                for (final c in annotationColors)
                  GestureDetector(
                    onTap: () {
                      if (!widget.canAnnotate) {
                        _needLogin();
                        return;
                      }
                      HapticFeedback.selectionClick();
                      Navigator.pop(
                        context,
                        AnnotationToolbarResult(
                          action: AnnotationSheetAction.armPaint,
                          color: c,
                        ),
                      );
                    },
                    child: Opacity(
                      opacity: widget.canAnnotate ? 1 : 0.4,
                      child: Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: annotationColorValue(c),
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: theme.colorScheme.outlineVariant,
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            if (widget.existing.isNotEmpty) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _noteCtrl,
                enabled: widget.canAnnotate,
                decoration: const InputDecoration(
                  labelText: '메모 (선택) — 첫 번째 주석',
                  border: OutlineInputBorder(),
                ),
                maxLines: 3,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  TextButton(
                    onPressed: !widget.canAnnotate
                        ? _needLogin
                        : () {
                            Navigator.pop(
                              context,
                              AnnotationToolbarResult(
                                action: AnnotationSheetAction.deleteAll,
                                color: _color,
                                existingId: _existingId,
                              ),
                            );
                          },
                    child: const Text('이 문장 주석 전부 삭제'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: !widget.canAnnotate
                        ? _needLogin
                        : () {
                            HapticFeedback.mediumImpact();
                            Navigator.pop(
                              context,
                              AnnotationToolbarResult(
                                action: AnnotationSheetAction.saveMeta,
                                color: _color,
                                note: _noteCtrl.text.trim(),
                                existingId: _existingId,
                              ),
                            );
                          },
                    child: const Text('메모 저장'),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 16),
            const Divider(),
            Row(
              children: [
                Text('AI로 묻기', style: theme.textTheme.titleSmall),
                const Spacer(),
                TextButton(
                  onPressed: _managePrompts,
                  child: const Text('관리'),
                ),
              ],
            ),
            if (_loadingPrompts)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              )
            else if (_prompts.isEmpty)
              Text(
                '저장된 프롬프트가 없습니다. 관리에서 추가하세요.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              )
            else
              for (final p in _prompts)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    p.body,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  trailing: const Icon(Icons.open_in_new, size: 18),
                  onTap: () {
                    HapticFeedback.selectionClick();
                    Navigator.pop(
                      context,
                      AnnotationToolbarResult(
                        action: AnnotationSheetAction.askAi,
                        promptBody: p.body,
                      ),
                    );
                  },
                ),
          ],
        ),
      ),
    );
  }
}

class _PromptManageSheet extends StatefulWidget {
  const _PromptManageSheet({
    required this.store,
    required this.initial,
    required this.onChanged,
  });

  final AiAskPromptStore store;
  final List<AiAskPrompt> initial;
  final ValueChanged<List<AiAskPrompt>> onChanged;

  @override
  State<_PromptManageSheet> createState() => _PromptManageSheetState();
}

class _PromptManageSheetState extends State<_PromptManageSheet> {
  late List<AiAskPrompt> _list;
  final _ctrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _list = List.of(widget.initial);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _persist() async {
    await widget.store.save(_list);
    // Seed flag stays true even if empty (182 J8).
    await widget.store.setSeeded(true);
    widget.onChanged(List.of(_list));
  }

  Future<void> _add() async {
    final body = _ctrl.text.trim();
    if (body.isEmpty) return;
    setState(() {
      _list = [
        ..._list,
        AiAskPrompt(
          id: newAiAskPromptId(),
          body: body,
          createdAt: DateTime.now().toUtc().toIso8601String(),
        ),
      ];
      _ctrl.clear();
    });
    await _persist();
  }

  Future<void> _edit(AiAskPrompt p) async {
    final ctrl = TextEditingController(text: p.body);
    final next = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('프롬프트 수정'),
        content: TextField(
          controller: ctrl,
          maxLines: 4,
          decoration: const InputDecoration(border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
            child: const Text('저장'),
          ),
        ],
      ),
    );
    ctrl.dispose();
    if (next == null || next.isEmpty) return;
    setState(() {
      _list = _list
          .map((e) => e.id == p.id ? e.copyWith(body: next) : e)
          .toList();
    });
    await _persist();
  }

  Future<void> _delete(AiAskPrompt p) async {
    setState(() => _list = _list.where((e) => e.id != p.id).toList());
    await _persist();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        16,
        8,
        16,
        16 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('프롬프트 관리', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            TextField(
              controller: _ctrl,
              decoration: const InputDecoration(
                labelText: '새 프롬프트',
                border: OutlineInputBorder(),
              ),
              maxLines: 2,
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(onPressed: _add, child: const Text('추가')),
            ),
            const Divider(),
            for (final p in _list)
              ListTile(
                title: Text(p.body, maxLines: 3, overflow: TextOverflow.ellipsis),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.edit_outlined),
                      onPressed: () => _edit(p),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () => _delete(p),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
