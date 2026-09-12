/// design/226 — full-screen PDF folder import (not thin sheet).
/// design/237 find CTA · 238 pick · 239 set row · 242 find-watch · 247 Downloads hint.
library;

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/pdf_folder_grant_models.dart';
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

class _PdfImportScreenState extends State<PdfImportScreen>
    with WidgetsBindingObserver {
  final Set<String> _selected = {};
  bool _busy = false;
  bool _unkeptOnly = false;
  String? _banner;
  bool _findWatchDialogOpen = false;
  Timer? _findWatchTimer;
  int _lastSetBuiltSig = -1;
  /// design/247 — offer Downloads pick once per find-watch arm after resume.
  bool _findWatchPickOffered = false;

  LibraryController get lib => widget.library;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    lib.notePickerSheetOpened();
    unawaited(_bootstrap());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _findWatchTimer?.cancel();
    lib.cancelPdfAdvisoryPump();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_onImportResume());
    }
  }

  Future<void> _onImportResume() async {
    await lib.rescanPdfFolderDebounced(trigger: 'import_resume');
    if (!mounted) return;
    await _maybeOfferDownloadsPickAfterFind();
  }

  /// design/247 — after 찾아보기, SI/main often lands in Downloads (outside tree).
  Future<void> _maybeOfferDownloadsPickAfterFind() async {
    if (!mounted) return;
    if (!lib.pdfFindWatchArmed || lib.pdfFindWatchHitDocUri != null) return;
    if (_findWatchPickOffered || _findWatchDialogOpen || _busy) return;
    if (lib.reanalyzing || lib.opening) return;
    _findWatchPickOffered = true;
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('다운로드에서 가져올까요?'),
        content: const Text(
          '브라우저에서 받은 PDF는 보통 다운로드 폴더에 있습니다. '
          '「받은 PDF 고르기」로 연결 폴더에 넣을까요?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('나중에'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('받은 PDF 고르기'),
          ),
        ],
      ),
    );
    if (!mounted) return;
    if (go == true) {
      await _pickReceived();
    }
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
      unawaited(lib.ensureVisiblePdfAdvisories());
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
      unawaited(lib.ensureVisiblePdfAdvisories());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _syncFindWatchTimer() {
    final armed = lib.pdfFindWatchArmed && lib.pdfFindWatchHitDocUri == null;
    if (armed && _findWatchTimer == null) {
      _findWatchTimer = Timer.periodic(const Duration(seconds: 4), (_) {
        unawaited(
          lib.rescanPdfFolderDebounced(
            trigger: 'find_watch',
            debounceMs: 500,
          ),
        );
      });
    } else if (!armed && _findWatchTimer != null) {
      _findWatchTimer?.cancel();
      _findWatchTimer = null;
    }
  }

  Future<void> _maybeShowFindWatchDialog() async {
    final hit = lib.pdfFindWatchHitDocUri;
    if (hit == null || _findWatchDialogOpen || !mounted) return;
    _findWatchDialogOpen = true;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('새 PDF가 폴더에 생겼습니다'),
        content: const Text(
          '찾아보기 후 연결된 폴더에 새 PDF가 감지되었습니다. 선택에 넣을까요?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('무시'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('선택에 넣기'),
          ),
        ],
      ),
    );
    if (!mounted) return;
    lib.confirmFindWatchHit(accepted: accepted == true);
    if (accepted == true) {
      setState(() => _selected.add(hit));
    }
    _findWatchDialogOpen = false;
  }

  Future<void> _openFind(ScannedPdfEntry e) async {
    final doi = e.advisoryDoi.trim();
    if (doi.isEmpty) return;
    final uri = Uri.parse('https://doi.org/$doi');
    try {
      final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
      lib.recordFindOpen(role: e.advisoryRole, ok: ok);
      if (ok) {
        lib.armFindWatch();
        _findWatchDialogOpen = false;
        _findWatchPickOffered = false;
        _syncFindWatchTimer();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                '브라우저에서 PDF를 받은 뒤 이 화면으로 돌아오면 '
                '다운로드에서 고를 수 있습니다. 연결 폴더에 바로 저장해도 됩니다.',
              ),
            ),
          );
        }
      }
    } catch (_) {
      lib.recordFindOpen(role: e.advisoryRole, ok: false, code: 'exc');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('링크를 열 수 없습니다.')),
        );
      }
    }
  }

  Future<void> _pickReceived() async {
    if (_busy || lib.reanalyzing || lib.opening) return;
    setState(() => _busy = true);
    try {
      final r = await lib.pickReceivedPdfsIntoFolder();
      if (!mounted) return;
      if (r.mode == 'cancel') return;
      final parts = <String>[];
      if (r.copied > 0) parts.add('폴더에 ${r.copied}건 복사');
      if (r.enqueued > 0) parts.add('대기열 ${r.enqueued}건');
      final msg = r.message ??
          (parts.isEmpty ? '처리하지 못했습니다.' : parts.join(' · '));
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _enqueueSelected(List<PdfImportListItem> listItems) async {
    if (_selected.isEmpty || lib.reanalyzing || lib.opening) return;
    setState(() => _busy = true);
    try {
      final remaining = Set<String>.from(_selected);
      var added = 0;
      var skipped = 0;
      String? message;

      for (final item in listItems) {
        if (item is! PdfImportSetItem) continue;
        if (!item.docUris.every(remaining.contains)) continue;
        remaining.removeAll(item.docUris);
        final outcome = await lib.enqueueFolderPdfSet(item.docUris);
        added += outcome.added;
        skipped += outcome.skipped;
        message ??= outcome.message;
      }
      if (remaining.isNotEmpty) {
        final outcome = await lib.enqueueFolderPdfs(remaining.toList());
        added += outcome.added;
        skipped += outcome.skipped;
        message ??= outcome.message;
      }

      if (!mounted) return;
      _selected.clear();
      final hint = lib.uploadBackgroundHint;
      if (hint != null && hint.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
      }
      if (message != null && message.isNotEmpty && added == 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
      } else if (added > 0) {
        final extra = skipped > 0 ? ' · 건너뜀 $skipped' : '';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('대기열에 $added건 추가$extra')),
        );
        Navigator.of(context).pop();
      } else if (skipped > 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('이미 대기열이거나 추가하지 못했습니다.')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toggleUris(List<String> uris) {
    setState(() {
      final allOn = uris.every(_selected.contains);
      if (allOn) {
        _selected.removeAll(uris);
      } else {
        _selected.addAll(uris);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: lib,
      builder: (context, _) {
        _syncFindWatchTimer();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          unawaited(_maybeShowFindWatchDialog());
        });

        final grant = lib.pdfFolderGrant;
        final entries = lib.pdfFolderEntries;
        final inLib = lib.libraryContentHashes;
        final queued = {for (final q in lib.uploadQueue) q.contentHash};
        final filtered = entries.where((e) {
          if (!_unkeptOnly) return true;
          final h = e.contentHash;
          if (h.length != 64) return true;
          return !inLib.contains(h);
        }).toList();

        final built = buildPdfImportListItems(filtered);
        final sig =
            built.nSets * 100000 + built.nSingles * 100 + built.nGap;
        if (sig != _lastSetBuiltSig && filtered.isNotEmpty) {
          _lastSetBuiltSig = sig;
          lib.recordImportSetBuilt(
            nSets: built.nSets,
            nSingles: built.nSingles,
            nGap: built.nGap,
          );
        }
        final listItems = built.items;

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
              if (lib.pdfFindWatchArmed && lib.pdfFindWatchHitDocUri == null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                  child: Text(
                    '찾아보기 후 연결 폴더의 새 PDF를 잠시 지켜보는 중…',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                        ),
                  ),
                ),
              if (grant != null && lib.pdfFolderWritable == false)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          '이 폴더는 읽기 전용입니다. PDF를 폴더로 복사하려면 쓰기 권한으로 다시 연결해 주세요.',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: Theme.of(context).colorScheme.error,
                              ),
                        ),
                      ),
                      TextButton(
                        onPressed: _busy ? null : _connectFolder,
                        child: const Text('다시 연결'),
                      ),
                    ],
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
                            onPickReceived: _busy ? null : _pickReceived,
                          )
                        : listItems.isEmpty
                            ? Center(
                                child: Text(
                                  _busy ? '목록 불러오는 중…' : '이 폴더에 PDF가 없습니다.',
                                  style: Theme.of(context).textTheme.bodyMedium,
                                ),
                              )
                            : ListView.separated(
                                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                                itemCount: listItems.length +
                                    (lib.pdfFolderTruncated ? 1 : 0) +
                                    1,
                                separatorBuilder: (_, __) =>
                                    const SizedBox(height: 6),
                                itemBuilder: (context, i) {
                                  if (lib.pdfFolderTruncated &&
                                      i == listItems.length) {
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
                                  final footerIndex = listItems.length +
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
                                  final item = listItems[i];
                                  if (item is PdfImportSetItem) {
                                    final sel =
                                        item.docUris.every(_selected.contains);
                                    return _SetRow(
                                      item: item,
                                      selected: sel,
                                      inLibrary: [
                                        item.main,
                                        item.si,
                                      ].every((e) =>
                                          e.contentHash.length == 64 &&
                                          inLib.contains(e.contentHash)),
                                      inQueue: [
                                        item.main,
                                        item.si,
                                      ].any((e) =>
                                          e.contentHash.length == 64 &&
                                          queued.contains(e.contentHash)),
                                      onToggle: () =>
                                          _toggleUris(item.docUris),
                                      // design/237 - set row already has mate; hide find CTA.
                                      onFindMain: null,
                                      onFindSi: null,
                                    );
                                  }
                                  final e =
                                      (item as PdfImportSingleItem).entry;
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
                                    onToggle: () => _toggleUris([e.docUri]),
                                    onFind: (e.advisoryDoi.trim().isEmpty ||
                                            matePresentForEntry(e, entries))
                                        ? null
                                        : () => unawaited(_openFind(e)),
                                  );
                                },
                              ),
              ),
              SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (grant != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: OutlinedButton.icon(
                            onPressed: _busy ||
                                    lib.reanalyzing ||
                                    lib.opening
                                ? null
                                : _pickReceived,
                            icon: const Icon(Icons.download_done_outlined),
                            label: const Text('받은 PDF 고르기'),
                          ),
                        ),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: _busy ||
                                      lib.reanalyzing ||
                                      lib.opening
                                  ? null
                                  : () async {
                                      await widget.onPickFromFiles();
                                      if (mounted) {
                                        Navigator.of(context).pop();
                                      }
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
                                  : () => _enqueueSelected(listItems),
                              child: Text(
                                '대기열에 추가 (${_selected.length})',
                              ),
                            ),
                          ),
                        ],
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
  const _EmptyConnect({
    required this.onConnect,
    required this.onSaf,
    required this.onPickReceived,
  });

  final VoidCallback? onConnect;
  final VoidCallback? onSaf;
  final VoidCallback? onPickReceived;

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
              onPressed: onPickReceived,
              child: const Text('받은 PDF 고르기'),
            ),
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
    this.onFind,
  });

  final ScannedPdfEntry entry;
  final bool selected;
  final bool inLibrary;
  final bool inQueue;
  final VoidCallback onToggle;
  final VoidCallback? onFind;

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
    final role = entry.advisoryRole.trim().toLowerCase();
    final showAdvisory = entry.advisoryState == PdfAdvisoryState.ready &&
        (entry.advisoryTitle.isNotEmpty ||
            role == 'main' ||
            role == 'supplementary');
    final titleLine = showAdvisory && entry.advisoryTitle.isNotEmpty
        ? entry.advisoryTitle
        : entry.displayName;
    final showFilenameSub = showAdvisory &&
        entry.advisoryTitle.isNotEmpty &&
        entry.advisoryTitle != entry.displayName;
    final roleChip = !showAdvisory
        ? null
        : (role == 'supplementary'
            ? '추정 SI'
            : (role == 'main' ? '추정 메인' : null));
    // Have SI → find main; have main (or unknown) → find SI.
    final findLabel =
        role == 'supplementary' ? '메인 찾아보기' : 'SI 찾아보기';
    final meta = [
      if (inLibrary) '이미 보관',
      if (inQueue) '대기열',
      if (entry.hashState == PdfHashState.computing) '확인 중',
      if (entry.advisoryState == PdfAdvisoryState.computing) '제목 확인 중',
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
                      titleLine,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    if (showFilenameSub) ...[
                      const SizedBox(height: 2),
                      Text(
                        entry.displayName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: scheme.onSurfaceVariant,
                            ),
                      ),
                    ],
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        if (roleChip != null)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: role == 'supplementary'
                                  ? scheme.tertiaryContainer
                                  : scheme.secondaryContainer,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              roleChip,
                              style: Theme.of(context)
                                  .textTheme
                                  .labelSmall
                                  ?.copyWith(
                                    color: role == 'supplementary'
                                        ? scheme.onTertiaryContainer
                                        : scheme.onSecondaryContainer,
                                  ),
                            ),
                          ),
                        if (onFind != null)
                          TextButton(
                            onPressed: onFind,
                            style: TextButton.styleFrom(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 0,
                              ),
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                            child: Text(findLabel),
                          ),
                        Text(
                          meta,
                          style:
                              Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: inLibrary
                                        ? Colors.green.shade700
                                        : scheme.onSurfaceVariant,
                                  ),
                        ),
                      ],
                    ),
                    if (showAdvisory) ...[
                      const SizedBox(height: 2),
                      Text(
                        '추정 · 업로드 후 확정',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: scheme.onSurfaceVariant,
                            ),
                      ),
                    ],
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

class _SetRow extends StatelessWidget {
  const _SetRow({
    required this.item,
    required this.selected,
    required this.inLibrary,
    required this.inQueue,
    required this.onToggle,
    this.onFindMain,
    this.onFindSi,
  });

  final PdfImportSetItem item;
  final bool selected;
  final bool inLibrary;
  final bool inQueue;
  final VoidCallback onToggle;
  final VoidCallback? onFindMain;
  final VoidCallback? onFindSi;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final border = inLibrary
        ? Border.all(color: Colors.green.shade600, width: 2)
        : Border.all(color: scheme.primary, width: 1.5);
    final title = item.main.advisoryTitle.isNotEmpty
        ? item.main.advisoryTitle
        : item.main.displayName;
    final meta = [
      '세트 · 메인+SI',
      if (inLibrary) '이미 보관',
      if (inQueue) '대기열',
      '대기열 2칸',
    ].join(' · ');

    return Material(
      color: scheme.surfaceContainerHighest.withValues(alpha: 0.35),
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
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${item.main.displayName} + ${item.si.displayName}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: scheme.primaryContainer,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            '메인+SI 세트',
                            style: Theme.of(context)
                                .textTheme
                                .labelSmall
                                ?.copyWith(color: scheme.onPrimaryContainer),
                          ),
                        ),
                        if (onFindMain != null)
                          TextButton(
                            onPressed: onFindMain,
                            style: TextButton.styleFrom(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 0,
                              ),
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                            child: const Text('메인 찾아보기'),
                          ),
                        if (onFindSi != null)
                          TextButton(
                            onPressed: onFindSi,
                            style: TextButton.styleFrom(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 0,
                              ),
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                            child: const Text('SI 찾아보기'),
                          ),
                        Text(
                          meta,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '추정 · 업로드 후 확정 · 자동 합치기 없음',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: scheme.onSurfaceVariant,
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

