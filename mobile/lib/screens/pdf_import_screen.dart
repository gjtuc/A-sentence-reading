/// design/226 — full-screen PDF folder import (not thin sheet).
library;

import 'dart:async';
import 'package:flutter/material.dart';
import '../api/pdf_folder_grant_models.dart';
import '../api/upload_picker_recent_models.dart';
import '../state/library_controller.dart';

class PdfImportScreen extends StatefulWidget {
  const PdfImportScreen({
    super.key,
    required this.library,
    required this.onPickFromFiles,
  });

  final LibraryController library;
  final Future<void> Function() onPickFromFiles;

  @override
  State<PdfImportScreen> createState() => _PdfImportScreenState();
}

class _PdfImportScreenState extends State<PdfImportScreen> {
  final Set<String> _selected = {};
  bool _busy = false;
  bool _unkeptOnly = false;
  String? _banner;

  LibraryController get lib => widget.library;

  @override
  void initState() {
    super.initState();
    lib.notePickerSheetOpened();
    unawaited(_bootstrap());
  }

  Future<void> _bootstrap() async {
    setState(() => _busy = true);
    try {
      await lib.loadPdfFolderGrantAndScan();
      final stale = lib.pdfFolderGrantStale;
      if (stale) {
        _banner = '이전에 연결한 폴더를 열 수 없습니다. 다시 연결해 주세요.';
      }
      unawaited(lib.ensureVisiblePdfHashes());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connectFolder() async {
    setState(() {
      _busy = true;
      _banner = null;
    });
    try {
      final ok = await lib.connectPdfFolder();
      if (!ok && mounted) {
        // cancel → silent
      }
      unawaited(lib.ensureVisiblePdfHashes());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _enqueueSelected() async {
    if (_selected.isEmpty || lib.reanalyzing || lib.opening) return;
    setState(() => _busy = true);
    try {
      final uris = _selected.toList();
      final outcome = await lib.enqueueFolderPdfs(uris);
      if (!mounted) return;
      _selected.clear();
      final hint = lib.uploadBackgroundHint;
      if (hint != null && hint.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
      }
      if (outcome.message != null && outcome.message!.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(outcome.message!)),
        );
      } else if (outcome.added > 0) {
        final extra =
            outcome.skipped > 0 ? ' · 건너뜀 ${outcome.skipped}' : '';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('대기열에 ${outcome.added}건 추가$extra')),
        );
        Navigator.of(context).pop();
      } else if (outcome.skipped > 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('이미 대기열이거나 추가하지 못했습니다.')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: lib,
      builder: (context, _) {
        final grant = lib.pdfFolderGrant;
        final entries = lib.pdfFolderEntries;
        final inLib = lib.libraryContentHashes;
        final queued = {for (final q in lib.uploadQueue) q.contentHash};
        final filtered = entries.where((e) {
          if (!_unkeptOnly) return true;
          final h = e.contentHash;
          if (h.length != 64) return true; // unknown → keep visible
          return !inLib.contains(h);
        }).toList();

        return Scaffold(
          appBar: AppBar(
            title: const Text('PDF 가져오기'),
            actions: [
              if (grant != null)
                TextButton(
                  onPressed: _busy ? null : _connectFolder,
                  child: const Text('폴더 변경'),
                ),
            ],
          ),
          body: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Text(
                  '초록 테두리 = 이미 보관함(내용 기준). 연결/병합과는 다릅니다.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
              if (_banner != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          _banner!,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      TextButton(
                        onPressed: _busy ? null : _connectFolder,
                        child: const Text('다시 연결'),
                      ),
                    ],
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        grant == null
                            ? '폴더 미연결'
                            : '폴더: ${grant.displayLabel}',
                        style: Theme.of(context).textTheme.titleSmall,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      '대기열 ${lib.uploadQueue.length}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              if (grant != null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Row(
                    children: [
                      FilterChip(
                        label: const Text('전체'),
                        selected: !_unkeptOnly,
                        onSelected: (_) => setState(() => _unkeptOnly = false),
                      ),
                      const SizedBox(width: 8),
                      FilterChip(
                        label: const Text('미보관만'),
                        selected: _unkeptOnly,
                        onSelected: (_) => setState(() => _unkeptOnly = true),
                      ),
                    ],
                  ),
                ),
              Expanded(
                child: _busy && entries.isEmpty && grant == null
                    ? const Center(child: CircularProgressIndicator())
                    : grant == null
                        ? _EmptyConnect(
                            onConnect: _busy ? null : _connectFolder,
                            onSaf: _busy
                                ? null
                                : () async {
                                    await widget.onPickFromFiles();
                                    if (mounted) Navigator.of(context).pop();
                                  },
                          )
                        : filtered.isEmpty
                            ? Center(
                                child: Text(
                                  _busy ? '목록 불러오는 중…' : '이 폴더에 PDF가 없습니다.',
                                  style: Theme.of(context).textTheme.bodyMedium,
                                ),
                              )
                            : ListView.separated(
                                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                                itemCount: filtered.length +
                                    (lib.pdfFolderTruncated ? 1 : 0) +
                                    1,
                                separatorBuilder: (_, __) =>
                                    const SizedBox(height: 6),
                                itemBuilder: (context, i) {
                                  if (lib.pdfFolderTruncated &&
                                      i == filtered.length) {
                                    return Padding(
                                      padding: const EdgeInsets.all(8),
                                      child: Text(
                                        '목록이 잘렸습니다(최대 $kPdfFolderScanMaxItems). '
                                        '「파일에서 추가」를 사용하세요.',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall,
                                      ),
                                    );
                                  }
                                  final footerIndex = filtered.length +
                                      (lib.pdfFolderTruncated ? 1 : 0);
                                  if (i == footerIndex) {
                                    return Padding(
                                      padding: const EdgeInsets.all(8),
                                      child: Text(
                                        '이 목록은 연결한 폴더(및 하위) 기준입니다. '
                                        '기기 전역 전수가 아닙니다.',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall
                                            ?.copyWith(
                                              color: Theme.of(context)
                                                  .colorScheme
                                                  .onSurfaceVariant,
                                            ),
                                      ),
                                    );
                                  }
                                  final e = filtered[i];
                                  final green = e.contentHash.length == 64 &&
                                      inLib.contains(e.contentHash);
                                  final inQ = e.contentHash.length == 64 &&
                                      queued.contains(e.contentHash);
                                  final sel = _selected.contains(e.docUri);
                                  return _FolderRow(
                                    entry: e,
                                    selected: sel,
                                    inLibrary: green,
                                    inQueue: inQ,
                                    onToggle: () {
                                      setState(() {
                                        if (sel) {
                                          _selected.remove(e.docUri);
                                        } else {
                                          _selected.add(e.docUri);
                                        }
                                      });
                                    },
                                  );
                                },
                              ),
              ),
              if (lib.pickerRecent.isNotEmpty)
                _RecentStrip(
                  recent: lib.pickerRecent,
                  inLib: inLib,
                  queued: queued,
                ),
              SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _busy || lib.reanalyzing || lib.opening
                              ? null
                              : () async {
                                  await widget.onPickFromFiles();
                                  if (mounted) Navigator.of(context).pop();
                                },
                          icon: const Icon(Icons.folder_open),
                          label: const Text('파일에서 추가'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: FilledButton(
                          onPressed: _busy ||
                                  _selected.isEmpty ||
                                  lib.reanalyzing ||
                                  lib.opening
                              ? null
                              : _enqueueSelected,
                          child: Text('대기열에 추가 (${_selected.length})'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _EmptyConnect extends StatelessWidget {
  const _EmptyConnect({required this.onConnect, required this.onSaf});

  final VoidCallback? onConnect;
  final VoidCallback? onSaf;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '자주 쓰는 논문 폴더를 연결하면\n파일 앱처럼 PDF 목록을 볼 수 있습니다.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onConnect,
              icon: const Icon(Icons.create_new_folder_outlined),
              label: const Text('논문 폴더 연결'),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: onSaf,
              child: const Text('또는 파일에서 추가'),
            ),
          ],
        ),
      ),
    );
  }
}

class _FolderRow extends StatelessWidget {
  const _FolderRow({
    required this.entry,
    required this.selected,
    required this.inLibrary,
    required this.inQueue,
    required this.onToggle,
  });

  final ScannedPdfEntry entry;
  final bool selected;
  final bool inLibrary;
  final bool inQueue;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final border = inLibrary
        ? Border.all(color: Colors.green.shade600, width: 2)
        : Border.all(color: scheme.outlineVariant);
    final sizeMb = entry.sizeBytes > 0
        ? (entry.sizeBytes / (1024 * 1024)).toStringAsFixed(2)
        : '?';
    String when = '';
    if (entry.lastModifiedMs > 0) {
      final d =
          DateTime.fromMillisecondsSinceEpoch(entry.lastModifiedMs).toLocal();
      when = '${d.month}/${d.day}';
    }
    final meta = [
      if (inLibrary) '이미 보관',
      if (inQueue) '대기열',
      if (entry.hashState == PdfHashState.computing) '확인 중',
      '${sizeMb}MB',
      if (when.isNotEmpty) when,
    ].join(' · ');

    return Material(
      color: scheme.surface,
      child: InkWell(
        onTap: onToggle,
        child: Container(
          decoration: BoxDecoration(
            border: border,
            borderRadius: BorderRadius.circular(8),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Checkbox(
                value: selected,
                onChanged: (_) => onToggle(),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      entry.displayName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      meta,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: inLibrary
                                ? Colors.green.shade700
                                : scheme.onSurfaceVariant,
                          ),
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
}

class _RecentStrip extends StatelessWidget {
  const _RecentStrip({
    required this.recent,
    required this.inLib,
    required this.queued,
  });

  final List<PickerRecentItem> recent;
  final Set<String> inLib;
  final Set<String> queued;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 72,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        itemCount: recent.length.clamp(0, 12),
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final item = recent[i];
          final green = inLib.contains(item.contentHash);
          return Container(
            width: 160,
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              border: Border.all(
                color: green ? Colors.green.shade600 : Theme.of(context).dividerColor,
                width: green ? 2 : 1,
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              item.displayName,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          );
        },
      ),
    );
  }
}
