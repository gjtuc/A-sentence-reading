import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/ai_ask_prompt_models.dart';
import '../api/ai_ask_prompt_store.dart';
import '../api/annotation_models.dart';
import '../api/voice_ask_models.dart';
import 'voice_ask_overlay.dart';

/// Bottom sheet: AI ask on top (design/471), then paint colors + memo
/// (design/166 · 182).
Future<AnnotationToolbarResult?> showAnnotationToolbarSheet({
  required BuildContext context,
  List<AnnotationEvent> existing = const [],
  bool canAnnotate = true,
  AiAskPromptStore? promptStore,
  String sentencePlain = '',
  VoiceAskSource? voice,
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
        sentencePlain: sentencePlain,
        voice: voice,
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
    this.sentencePlain = '',
    this.voice,
  });

  final List<AnnotationEvent> existing;
  final bool canAnnotate;
  final AiAskPromptStore promptStore;
  final String sentencePlain;
  final VoiceAskSource? voice;

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
            if (widget.sentencePlain.trim().isNotEmpty) ...[
              Text(
                widget.sentencePlain.trim(),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 8),
            ],
            AiAskQuestionField(
              voice: widget.voice,
              onAsk: (q) => Navigator.pop(
                context,
                AnnotationToolbarResult(
                  action: AnnotationSheetAction.askAi,
                  promptBody: q,
                ),
              ),
            ),
            const SizedBox(height: 4),
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
            const SizedBox(height: 8),
            const Divider(),
            Text('하이라이트', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(
              widget.canAnnotate
                  ? '색을 고른 뒤 단어를 문지르세요 (꾹 누를 필요 없음)'
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
          ],
        ),
      ),
    );
  }
}

/// design/419 — a question typed now, sent with the sentence on Enter.
class AiAskQuestionField extends StatefulWidget {
  const AiAskQuestionField({
    super.key,
    required this.onAsk,
    this.initial = '',
    this.autofocus = false,
    this.compact = kIsWeb,
    this.voice,
  });

  final ValueChanged<String> onAsk;
  final String initial;
  final bool autofocus;
  /// design/472 — the web keeps the thin box; a long question wraps to two lines.
  final bool compact;

  /// design/475 — null hides the microphone.
  final VoiceAskSource? voice;

  @override
  State<AiAskQuestionField> createState() => _AiAskQuestionFieldState();
}

class _AiAskQuestionFieldState extends State<AiAskQuestionField> {
  late final TextEditingController _ctrl =
      TextEditingController(text: widget.initial)..addListener(_onText);
  final FocusNode _focus = FocusNode();

  /// design/475 — the box holds words the microphone wrote down. Edits keep
  /// it; emptying the box to type afresh drops it.
  bool _spoken = false;

  void _onText() {
    if (_spoken && _ctrl.text.trim().isEmpty) _spoken = false;
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send() {
    final q = _ctrl.text.trim();
    if (q.isEmpty) return;
    widget.onAsk(voiceAskPrompt(q, spoken: _spoken));
  }

  Future<void> _speak() async {
    final voice = widget.voice;
    if (voice == null) return;
    final text = await showVoiceAskOverlay(context, source: voice);
    if (!mounted || text == null || text.trim().isEmpty) return;
    final had = _ctrl.text.trim();
    final next = had.isEmpty ? text.trim() : '$had ${text.trim()}';
    _ctrl.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: next.length),
    );
    _spoken = true;
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    // design/471 — several lines tall and wrapping, but still one line of text:
    // Enter and the keyboard's send key send it, so there is no line break.
    final send = IconButton(
      tooltip: 'Google AI에 묻기',
      icon: const Icon(Icons.send),
      onPressed: _send,
    );
    return TextField(
      controller: _ctrl,
      focusNode: _focus,
      autofocus: widget.autofocus,
      keyboardType: TextInputType.text,
      textInputAction: TextInputAction.send,
      minLines: widget.compact ? 1 : 3,
      maxLines: widget.compact ? 2 : 5,
      style: widget.compact ? null : const TextStyle(fontSize: 16),
      onSubmitted: (_) => _send(),
      decoration: InputDecoration(
        hintText: '질문을 입력하고 Enter',
        border: const OutlineInputBorder(),
        isDense: widget.compact,
        suffixIcon: widget.voice == null
            ? send
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    key: const ValueKey('ai_ask_mic'),
                    tooltip: '말로 묻기',
                    icon: const Icon(Icons.mic_none),
                    onPressed: () => unawaited(_speak()),
                  ),
                  send,
                ],
              ),
      ),
    );
  }
}

/// design/419 — a typed letter or Enter opens the question box; shortcuts with
/// Ctrl, Alt or Cmd, the arrows and Space do not. The letter itself is dropped:
/// with no text field focused the browser types Latin letters even in Korean
/// mode, so keeping it would start a Korean question with a stray letter.
bool aiAskOpensOnKey(
  KeyEvent event, {
  required bool ctrl,
  required bool alt,
  required bool meta,
}) {
  if (event is! KeyDownEvent || ctrl || alt || meta) return false;
  final key = event.logicalKey;
  if (key == LogicalKeyboardKey.enter || key == LogicalKeyboardKey.numpadEnter) {
    return true;
  }
  final ch = event.character;
  if (ch == null || ch.trim().isEmpty) return false;
  return ch.runes.every((r) => r >= 0x21 && r != 0x7f);
}

/// design/419 — the web reader's keyboard: a key opens this, the question is
/// typed, Enter sends it with the sentence. Saved prompts sit below as chips.
Future<String?> showAiAskTypeDialog({
  required BuildContext context,
  required String sentencePlain,
  AiAskPromptStore? promptStore,
  VoiceAskSource? voice,
}) {
  return showDialog<String>(
    context: context,
    builder: (ctx) => _AiAskTypeDialog(
      sentencePlain: sentencePlain,
      store: promptStore ?? PrefsAiAskPromptStore(),
      voice: voice,
    ),
  );
}

class _AiAskTypeDialog extends StatefulWidget {
  const _AiAskTypeDialog({
    required this.sentencePlain,
    required this.store,
    this.voice,
  });

  final String sentencePlain;
  final AiAskPromptStore store;
  final VoiceAskSource? voice;

  @override
  State<_AiAskTypeDialog> createState() => _AiAskTypeDialogState();
}

class _AiAskTypeDialogState extends State<_AiAskTypeDialog> {
  List<AiAskPrompt> _prompts = const [];

  @override
  void initState() {
    super.initState();
    unawaited(() async {
      final list = await loadAiAskPromptsEnsuringSeed(widget.store);
      if (mounted) setState(() => _prompts = list);
    }());
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: const Text('이 문장을 AI에게 묻기'),
      content: SizedBox(
        width: 560,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.sentencePlain,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            AiAskQuestionField(
              autofocus: true,
              voice: widget.voice,
              onAsk: (q) => Navigator.pop(context, q),
            ),
            if (_prompts.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final p in _prompts)
                    ActionChip(
                      label: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 480),
                        child: Text(p.body, overflow: TextOverflow.ellipsis),
                      ),
                      onPressed: () => Navigator.pop(context, p.body),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('닫기'),
        ),
      ],
    );
  }
}

/// design/434 — what the figure dialog asks for. An empty [question] copies the
/// figure alone; the question is then typed on the AI page.
class FigureAiAsk {
  const FigureAiAsk(this.question);

  final String question;
}

/// design/434 — the figure window's question box. The AI page keeps only the
/// picture when a picture and text are pasted together, so the question goes
/// to the clipboard first and the picture after it: Ctrl+V pastes the picture
/// and Win+V's list still holds the question.
Future<FigureAiAsk?> showFigureAiAskDialog({
  required BuildContext context,
  required Uint8List image,
  AiAskPromptStore? promptStore,
}) {
  return showDialog<FigureAiAsk>(
    context: context,
    builder: (ctx) => _FigureAiAskDialog(
      image: image,
      store: promptStore ?? PrefsAiAskPromptStore(),
    ),
  );
}

const kFigureAiAskSteps = [
  '질문을 적거나 아래 질문을 고르면, 그림과 질문이 복사되고 AI 창이 열려요.',
  'AI 창 입력칸을 누르고 Ctrl+V 를 누르면 그림이 들어가요.',
  '이어서 Win+V 를 누르고, 목록에서 질문 글을 눌러 넣은 뒤 Enter 를 눌러요. '
      '(Win+V 가 처음이면 "켜기"를 한 번 눌러 주세요.)',
];

class _FigureAiAskDialog extends StatefulWidget {
  const _FigureAiAskDialog({required this.image, required this.store});

  final Uint8List image;
  final AiAskPromptStore store;

  @override
  State<_FigureAiAskDialog> createState() => _FigureAiAskDialogState();
}

class _FigureAiAskDialogState extends State<_FigureAiAskDialog> {
  List<AiAskPrompt> _prompts = const [];

  @override
  void initState() {
    super.initState();
    unawaited(() async {
      final list = await loadAiAskPromptsEnsuringSeed(widget.store);
      if (mounted) setState(() => _prompts = list);
    }());
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final steps = theme.textTheme.bodyMedium?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );
    return AlertDialog(
      title: const Text('이 그림을 AI에게 묻기'),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 220),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: Image.memory(widget.image, fit: BoxFit.contain),
                ),
              ),
              const SizedBox(height: 12),
              Text('쓰는 법', style: theme.textTheme.titleSmall),
              const SizedBox(height: 4),
              for (var i = 0; i < kFigureAiAskSteps.length; i++)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text('${i + 1}. ${kFigureAiAskSteps[i]}', style: steps),
                ),
              const SizedBox(height: 12),
              AiAskQuestionField(
                autofocus: true,
                onAsk: (q) => Navigator.pop(context, FigureAiAsk(q)),
              ),
              if (_prompts.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final p in _prompts)
                      ActionChip(
                        label: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 480),
                          child: Text(p.body, overflow: TextOverflow.ellipsis),
                        ),
                        onPressed: () => Navigator.pop(context, FigureAiAsk(p.body)),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, const FigureAiAsk('')),
          child: const Text('그림만 복사하고 AI 열기'),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('닫기'),
        ),
      ],
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
