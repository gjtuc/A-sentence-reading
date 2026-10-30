/// design/490 — a library card's own title (typed or spoken) and kind.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/paper_models.dart';
import '../state/paper_labels.dart';
import 'voice_ask_overlay.dart';

const String kTitleVoiceListening = '새 제목을 말해 주세요.';
const String kTitleVoiceTapToEnd = '아무 곳이나 누르면 끝나요.';

const List<(String, String)> kPaperKindChoices = [
  ('paper', '논문'),
  ('review', '심사 기록'),
  ('general', '일반 글'),
];

/// The new title, or null when cancelled. [voice] builds the microphone source
/// from the title in the field; null hides the microphone.
Future<String?> showPaperTitleDialog(
  BuildContext context, {
  required PaperEntry entry,
  VoiceAskSource Function(String current)? voice,
}) {
  return showDialog<String>(
    context: context,
    builder: (ctx) => _PaperTitleDialog(entry: entry, voice: voice),
  );
}

class _PaperTitleDialog extends StatefulWidget {
  const _PaperTitleDialog({required this.entry, this.voice});

  final PaperEntry entry;
  final VoiceAskSource Function(String current)? voice;

  @override
  State<_PaperTitleDialog> createState() => _PaperTitleDialogState();
}

class _PaperTitleDialogState extends State<_PaperTitleDialog> {
  late final TextEditingController _ctrl =
      TextEditingController(text: widget.entry.shownTitle);
  final FocusNode _focus = FocusNode();

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _put(String text) {
    _ctrl.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    setState(() {});
  }

  Future<void> _speak() async {
    final voice = widget.voice;
    if (voice == null) return;
    final text = await showVoiceAskOverlay(context, source: voice(_ctrl.text));
    if (!mounted || text == null || text.trim().isEmpty) return;
    _put(cleanPaperLabelTitle(text));
    _focus.requestFocus();
  }

  void _save() {
    final t = cleanPaperLabelTitle(_ctrl.text);
    if (t.isEmpty) return;
    Navigator.of(context).pop(t);
  }

  @override
  Widget build(BuildContext context) {
    final analysed = widget.entry.title;
    final changed = cleanPaperLabelTitle(_ctrl.text) != cleanPaperLabelTitle(analysed);
    return AlertDialog(
      title: const Text('제목 고치기'),
      content: SizedBox(
        width: 480,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              key: const ValueKey('paper_title_field'),
              controller: _ctrl,
              focusNode: _focus,
              autofocus: true,
              minLines: 1,
              maxLines: 4,
              maxLength: kPaperLabelTitleMax,
              textInputAction: TextInputAction.done,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => _save(),
              decoration: InputDecoration(
                border: const OutlineInputBorder(),
                suffixIcon: widget.voice == null
                    ? null
                    : IconButton(
                        key: const ValueKey('paper_title_mic'),
                        tooltip: '말로 제목 쓰기',
                        icon: const Icon(Icons.mic_none),
                        onPressed: () => unawaited(_speak()),
                      ),
              ),
            ),
            if (changed) ...[
              Text(
                '분석한 제목: $analysed',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              TextButton(
                key: const ValueKey('paper_title_reset'),
                onPressed: () => _put(analysed),
                child: const Text('분석한 제목으로 되돌리기'),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        FilledButton(
          key: const ValueKey('paper_title_save'),
          onPressed: cleanPaperLabelTitle(_ctrl.text).isEmpty ? null : _save,
          child: const Text('저장'),
        ),
      ],
    );
  }
}

/// The chosen kind, or null when cancelled.
Future<String?> showPaperKindDialog(
  BuildContext context, {
  required PaperEntry entry,
}) {
  return showDialog<String>(
    context: context,
    builder: (ctx) => _PaperKindDialog(entry: entry),
  );
}

class _PaperKindDialog extends StatefulWidget {
  const _PaperKindDialog({required this.entry});

  final PaperEntry entry;

  @override
  State<_PaperKindDialog> createState() => _PaperKindDialogState();
}

class _PaperKindDialogState extends State<_PaperKindDialog> {
  late String _kind = widget.entry.effectiveKind;

  @override
  Widget build(BuildContext context) {
    final auto = widget.entry.docKind;
    return AlertDialog(
      title: const Text('종류 바꾸기'),
      content: RadioGroup<String>(
        groupValue: _kind,
        onChanged: (v) {
          if (v != null) setState(() => _kind = v);
        },
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (value, label) in kPaperKindChoices)
              RadioListTile<String>(
                key: ValueKey('paper_kind_$value'),
                contentPadding: EdgeInsets.zero,
                value: value,
                title: Text(label),
                subtitle: value == auto ? const Text('자동 판단') : null,
              ),
            Text(
              '논문만 보충 자료와 짝을 지어요.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        FilledButton(
          key: const ValueKey('paper_kind_save'),
          onPressed: () => Navigator.of(context).pop(_kind),
          child: const Text('저장'),
        ),
      ],
    );
  }
}
