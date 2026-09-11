import 'dart:async';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../api/ingest_models.dart';
import '../api/library_reorder_proxy.dart';
import '../api/paper_models.dart';
import '../state/annotation_controller.dart';
import '../state/auth_controller.dart';
import '../state/bookmark_controller.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../widgets/upload_queue_sheet.dart';
import 'pdf_import_screen.dart';
import '../widgets/upload_status_bar.dart';

/// Authenticated paper list → open · PDF upload queue (design/62 · 70 · 221 · 224).
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({
    super.key,
    required this.auth,
    required this.library,
    required this.bookmarks,
    this.annotations,
    this.shadowing,
    this.onOpened,
    this.onOpenSettings,
  });

  final AuthController auth;
  final LibraryController library;
  final BookmarkController bookmarks;
  final AnnotationController? annotations;
  final ShadowingController? shadowing;

  /// Called after a successful open (e.g. show reader surface).
  final VoidCallback? onOpened;

  /// design/224 — gear opens Settings (no bottom tab).
  final VoidCallback? onOpenSettings;

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  /// design/224 — long-press enters edit; trash only while editing.
  bool _selecting = false;
  final Set<String> _selected = <String>{};
  bool _deleting = false;

  /// design/225-F — magnetic trash while reordering.
  final GlobalKey _trashKey = GlobalKey();
  String? _dragCacheId;
  bool _dragOverTrash = false;
  static const double _magnetPad = 28;

  /// design/168c — non-ok ingest_status chip label (null = hide).
  static String? _ingestStatusLabel(String status) {
    switch (status.trim().toLowerCase()) {
      case 'partial':
        return '부분 저장';
      case 'processing':
        return '분석 중';
      case 'error':
        return '실패';
      default:
        return null;
    }
  }

  @override
  void initState() {
    super.initState();
    widget.auth.addListener(_onAuth);
    // Load when already logged in at first frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.auth.isLoggedIn) {
        _loadAndResume();
      }
    });
  }

  @override
  void dispose() {
    widget.auth.removeListener(_onAuth);
    super.dispose();
  }

  void _onAuth() {
    if (widget.auth.isLoggedIn) {
      _loadAndResume();
    } else {
      // WHY (MULTI-USER): wipe list + upload draft so next account cannot resume.
      setState(() {
        _selecting = false;
        _selected.clear();
      });
      widget.library.clearAll();
    }
  }

  void _enterEdit(String id) {
    setState(() {
      _selecting = true;
      _selected
        ..clear()
        ..add(id);
    });
  }

  void _exitEdit() {
    setState(() {
      _selecting = false;
      _selected.clear();
    });
  }

  void _toggleSelected(String id) {
    setState(() {
      if (_selected.contains(id)) {
        _selected.remove(id);
      } else {
        _selected.add(id);
      }
    });
  }

  /// design/224 · 225 — soft-hide + SnackBar undo; hard DELETE after grace.
  Future<void> _softHideWithUndo(List<String> ids) async {
    if (_deleting || ids.isEmpty) return;
    setState(() => _deleting = true);
    final hidden = await widget.library.softHidePapers(ids);
    if (!mounted) return;
    setState(() {
      _deleting = false;
      for (final id in ids) {
        _selected.remove(id);
      }
      if (_selected.isEmpty) {
        _selecting = false;
      }
      _dragCacheId = null;
      _dragOverTrash = false;
    });
    if (hidden == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(widget.library.error ?? '숨기기에 실패했습니다.'),
        ),
      );
      return;
    }
    ScaffoldMessenger.of(context).clearSnackBars();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        duration: const Duration(seconds: 60),
        content: Text('$hidden건을 숨겼습니다. 1분 후 영구 삭제됩니다.'),
        action: SnackBarAction(
          label: '실행 취소',
          onPressed: () {
            unawaited(widget.library.undoSoftHide(ids));
          },
        ),
      ),
    );
  }

  Future<void> _confirmDelete() async {
    if (_deleting || _selected.isEmpty) return;
    await _softHideWithUndo(_selected.toList(growable: false));
  }

  void _updateTrashHover(Offset globalPos) {
    final ctx = _trashKey.currentContext;
    if (ctx == null) return;
    final box = ctx.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    final origin = box.localToGlobal(Offset.zero);
    final rect = (origin & box.size).inflate(_magnetPad);
    final hit = rect.contains(globalPos);
    if (hit != _dragOverTrash) {
      setState(() => _dragOverTrash = hit);
    }
  }

  Future<void> _showRetentionSheet(PaperEntry entry) async {
    if (!entry.retentionWarn) return;
    final days = entry.retentionDaysUntilExpiry;
    final extendDays = entry.retentionExtendDays;
    final ok = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '보관 기한',
                style: Theme.of(ctx).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(
                days != null
                    ? '약 $days일 후 이 논문과 노트·연습 기록이 삭제됩니다.'
                    : '곧 보관 기한이 끝납니다.',
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: entry.retentionCanExtend
                    ? () => Navigator.pop(ctx, true)
                    : null,
                child: Text('$extendDays일 연장'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('닫기'),
              ),
            ],
          ),
        );
      },
    );
    if (ok != true || !mounted) return;
    final extended = await widget.library.extendRetention(entry);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          extended
              ? '보관 기한을 $extendDays일 연장했습니다.'
              : (widget.library.error ?? '연장에 실패했습니다.'),
        ),
      ),
    );
  }

  Future<void> _mergeSupplementary(PaperEntry entry) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('보충자료 합치기'),
        content: Text(
          '「${entry.title}」의 보충자료를 본문 뒤에 합칩니다.\n'
          '합친 뒤에는 보충 항목이 목록에서 숨겨집니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('합치기'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final ok = await widget.library.mergeSupplementary(entry);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok
              ? '보충자료를 합쳤습니다.'
              : (widget.library.error ?? '합치기에 실패했습니다.'),
        ),
      ),
    );
  }

  Future<void> _loadAndResume() async {
    await widget.library.refresh();
    if (!mounted || !widget.auth.isLoggedIn) return;
    // design/71 — app auto-resumes processing / local draft without a second tap.
    final result = await widget.library.resumePendingIfAny();
    if (!mounted) return;
    await _afterResumeResult(result);
  }

  Future<void> _resumeInterrupted() async {
    final result = await widget.library.onAppResumed();
    if (!mounted) return;
    await _afterResumeResult(result);
  }

  Future<void> _resumeAndOpen() async {
    final result = await widget.library.resumeAnalysis();
    if (!mounted) return;
    await _afterResumeResult(result);
  }

  Future<void> _afterResumeResult(IngestJobResult? result) async {
    final hint = widget.library.uploadBackgroundHint;
    if (hint != null && hint.isNotEmpty && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
    }
    if (result == null) {
      if (widget.library.error != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(widget.library.error!)),
        );
      }
      return;
    }
    PaperEntry? entry;
    for (final p in widget.library.papers) {
      if (p.id == result.cacheId) {
        entry = p;
        break;
      }
    }
    if (entry != null) {
      await _open(entry);
    }
  }

  Future<void> _open(entry) async {
    final o = await widget.library.open(entry);
    if (!mounted) return;
    if (o == null) {
      final msg = widget.library.error ?? '열기에 실패했습니다.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('열림: ${o.title.isEmpty ? o.sessionId : o.title}')),
    );
    widget.onOpened?.call();
  }

  Future<void> _maybeAutoOpenFromQueue() async {
    final lib = widget.library;
    final cid = (lib.pendingAutoOpenCacheId ?? '').trim();
    if (cid.isEmpty) return;
    lib.consumePendingAutoOpen();
    PaperEntry? entry;
    for (final p in lib.papers) {
      if (p.id == cid) {
        entry = p;
        break;
      }
    }
    if (entry == null) return;
    await _open(entry);
  }

  Future<void> _openUploadPicker() async {
    final lib = widget.library;
    if (lib.reanalyzing || lib.opening) return;
    // design/226 — full-screen folder browser (SAF escape still inside).
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => PdfImportScreen(
          library: lib,
          onPickFromFiles: _pickAndUpload,
        ),
      ),
    );
  }

  Future<void> _pickAndUpload() async {
    final lib = widget.library;
    // design/221 — allow enqueue while an analysis is already running.
    if (lib.reanalyzing || lib.opening) return;

    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf'],
      allowMultiple: true,
      withData: true,
    );
    if (!mounted) return;
    if (picked == null || picked.files.isEmpty) {
      // EDGE: user cancelled — stay silent (not a failure snackbar).
      return;
    }
    final batch = <({String name, Uint8List bytes})>[];
    for (final f in picked.files) {
      final name = f.name.trim();
      final bytes = f.bytes;
      if (name.isEmpty || bytes == null || bytes.isEmpty) {
        continue;
      }
      batch.add((name: name, bytes: bytes));
    }
    if (batch.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('파일을 읽지 못했습니다. 다른 PDF를 골라 주세요.')),
      );
      return;
    }

    final outcome = await lib.enqueuePickedPdfs(batch);
    if (!mounted) return;
    final hint = lib.uploadBackgroundHint;
    if (hint != null && hint.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
    }
    if (outcome.message != null && outcome.message!.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(outcome.message!)),
      );
    } else if (outcome.added > 0) {
      final extra = outcome.skipped > 0 ? ' · 건너뜀 ${outcome.skipped}' : '';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('대기열에 ${outcome.added}건 추가$extra')),
      );
    } else if (outcome.skipped > 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('이미 대기열이거나 추가하지 못했습니다.')),
      );
    }
    // design/221 first_only — open when pump sets pendingAutoOpenCacheId.
    await _maybeAutoOpenFromQueue();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([widget.auth, widget.library, widget.bookmarks]),
      builder: (context, _) {
        final pendingOpen = widget.library.pendingAutoOpenCacheId;
        if (pendingOpen != null && pendingOpen.trim().isNotEmpty) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            unawaited(_maybeAutoOpenFromQueue());
          });
        }
        if (!widget.auth.isLoggedIn) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                '보관 목록을 보려면 먼저 로그인하세요.',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        final lib = widget.library;
        if (lib.loading && lib.papers.isEmpty && !lib.uploading && !lib.reanalyzing) {
          return const Center(child: CircularProgressIndicator());
        }
        return PopScope(
          canPop: !_selecting,
          onPopInvokedWithResult: (didPop, _) {
            if (didPop) return;
            if (_selecting) _exitEdit();
          },
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _selecting
                                  ? (_selected.isEmpty
                                      ? '편집'
                                      : '${_selected.length}건 선택')
                                  : '보관 ${lib.papers.length}건',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                          ],
                        ),
                      ),
                      if (_selecting) ...[
                        IconButton(
                          onPressed: _deleting ? null : _exitEdit,
                          icon: const Icon(Icons.close),
                          tooltip: '편집 종료',
                        ),
                        IconButton(
                          key: _trashKey,
                          onPressed: _deleting || _selected.isEmpty
                              ? null
                              : _confirmDelete,
                          icon: _deleting
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : AnimatedScale(
                                  scale: _dragOverTrash ? 1.25 : 1.0,
                                  duration: const Duration(milliseconds: 120),
                                  child: Icon(
                                    Icons.delete_outline,
                                    color: _dragOverTrash
                                        ? Theme.of(context).colorScheme.error
                                        : null,
                                  ),
                                ),
                          tooltip: '숨기기',
                        ),
                      ],
                      if (lib.uploadQueue.isNotEmpty)
                        IconButton(
                          onPressed: () => showUploadQueueSheet(
                            context: context,
                            library: lib,
                          ),
                          icon: Badge(
                            label: Text('${lib.uploadQueue.length}'),
                            child: const Icon(Icons.queue),
                          ),
                          tooltip: '업로드 대기열',
                        ),
                      IconButton(
                        // design/221 — enqueue allowed while analyzing.
                        onPressed: lib.loading ||
                                lib.opening ||
                                lib.reanalyzing ||
                                _deleting
                            ? null
                            : _openUploadPicker,
                        icon: const Icon(Icons.upload_file),
                        tooltip: 'PDF 가져오기',
                      ),
                      IconButton(
                        onPressed: widget.onOpenSettings,
                        icon: const Icon(Icons.settings_outlined),
                        tooltip: '설정',
                      ),
                    ],
                  ),
                ),
              ),
              if (_selecting)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      '체크 후 휴지통으로 숨깁니다. 1분 안 실행 취소 가능.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                )
              else if (!lib.uploading && !lib.reanalyzing)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      '길게 눌러 편집 · 편집 중 끌어 순서 변경.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ),
              if (lib.translateBackfillBusy || lib.shadowingChunksBusy || lib.pendingEnrichBusy)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const LinearProgressIndicator(),
                        const SizedBox(height: 6),
                        Text(
                          (lib.shadowingChunksProgress == null ||
                                  lib.shadowingChunksProgress!.isEmpty)
                              ? '번역·연습 준비 중'
                              : '번역·연습 준비 중 · ${lib.shadowingChunksProgress}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        Text(
                          '앱을 열어 두면 계속됩니다. 화면이 오래 꺼지면 중단될 수 있어요.',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: Theme.of(context)
                                    .colorScheme
                                    .onSurfaceVariant,
                              ),
                        ),
                      ],
                    ),
                  ),
                ),
              if (lib.reanalyzing || lib.uploading || lib.uploadQueue.isNotEmpty)
                SliverToBoxAdapter(
                  child: UploadStatusBar(
                    library: lib,
                    onResume: _resumeInterrupted,
                  ),
                ),
              if (lib.error != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 8, 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            lib.error!,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: lib.dismissError,
                          icon: const Icon(Icons.close),
                          tooltip: '닫기',
                          visualDensity: VisualDensity.compact,
                        ),
                      ],
                    ),
                  ),
                ),
              if (lib.resumeOfferVisible && !lib.uploading && !lib.reanalyzing)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        FilledButton.icon(
                          onPressed: lib.opening
                              ? null
                              : () => _resumeAndOpen(),
                          icon: const Icon(Icons.play_arrow),
                          label: const Text('이어서 분석하기'),
                        ),
                        TextButton(
                          onPressed: lib.discardResumeDraft,
                          child: const Text('초안 삭제'),
                        ),
                      ],
                    ),
                  ),
                ),
              if (lib.papers.isEmpty && !lib.uploading && !lib.reanalyzing)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Text(
                            '아직 보관한 논문이 없습니다.\n'
                            'PDF를 고르면 분석이 끝난 뒤\n'
                            '이 기기에 보관됩니다.',
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 16),
                          FilledButton.tonalIcon(
                            onPressed: lib.loading || lib.reanalyzing || lib.opening
                                ? null
                                : _openUploadPicker,
                            icon: const Icon(Icons.upload_file),
                            label: const Text('PDF 가져오기'),
                          ),
                        ],
                      ),
                    ),
                  ),
                )
              else if (lib.papers.isNotEmpty)
                SliverReorderableList(
                  itemCount: lib.papers.length,
                  // design/122 — custom proxy: no M3 white flash; keep lifted row.
                  // design/225-F — Listener for magnetic trash hit-test.
                  proxyDecorator: (child, index, animation) {
                    final scheme = Theme.of(context).colorScheme;
                    final base = libraryReorderProxyDecorator(
                      child,
                      index,
                      animation,
                      colorScheme: scheme,
                    );
                    return Listener(
                      onPointerMove: (e) => _updateTrashHover(e.position),
                      child: base,
                    );
                  },
                  onReorderStart: (index) {
                    if (index < 0 || index >= lib.papers.length) return;
                    setState(() {
                      _dragCacheId = lib.papers[index].id;
                      _dragOverTrash = false;
                    });
                  },
                  onReorderEnd: (_) {
                    if (_dragOverTrash) {
                      // Drop handled in onReorder; clear leftover flags.
                    }
                    if (mounted && !_deleting) {
                      setState(() {
                        if (!_dragOverTrash) {
                          _dragCacheId = null;
                          _dragOverTrash = false;
                        }
                      });
                    }
                  },
                  onReorder: (oldIndex, newIndex) {
                    // design/224 — reorder only in edit mode.
                    if (!_selecting ||
                        lib.opening ||
                        lib.uploading ||
                        lib.reanalyzing ||
                        _deleting) {
                      setState(() {
                        _dragCacheId = null;
                        _dragOverTrash = false;
                      });
                      return;
                    }
                    // design/225-F — trash magnet: soft-hide, no order persist.
                    if (_dragOverTrash) {
                      final id = _dragCacheId;
                      setState(() {
                        _dragOverTrash = false;
                        _dragCacheId = null;
                      });
                      if (id != null && id.isNotEmpty) {
                        unawaited(_softHideWithUndo([id]));
                      }
                      return;
                    }
                    unawaited(lib.reorderPapers(oldIndex, newIndex));
                    setState(() {
                      _dragCacheId = null;
                      _dragOverTrash = false;
                    });
                  },
                  itemBuilder: (context, i) {
                    final e = lib.papers[i];
                    final selected = _selected.contains(e.id);
                    final bookmarkCount = widget.bookmarks.paperBookmarkCount(e.id);
                    final tile = ListTile(
                      leading: _selecting
                          ? Checkbox(
                              value: selected,
                              onChanged: _deleting
                                  ? null
                                  : (_) => _toggleSelected(e.id),
                            )
                          : null,
                      title: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (e.libraryTag.isNotEmpty && e.libraryTag != '로컬')
                            Padding(
                              padding: const EdgeInsets.only(bottom: 4),
                              child: Chip(
                                label: Text(
                                  e.libraryTag,
                                  style: const TextStyle(fontSize: 11),
                                ),
                                visualDensity: VisualDensity.compact,
                                materialTapTargetSize:
                                    MaterialTapTargetSize.shrinkWrap,
                                padding: EdgeInsets.zero,
                              ),
                            ),
                          Row(
                            children: [
                              Expanded(child: Text(e.title)),
                              if (_ingestStatusLabel(e.ingestStatus) != null)
                                Padding(
                                  padding: const EdgeInsets.only(left: 8),
                                  child: Chip(
                                    label: Text(
                                      _ingestStatusLabel(e.ingestStatus)!,
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                    visualDensity: VisualDensity.compact,
                                    materialTapTargetSize:
                                        MaterialTapTargetSize.shrinkWrap,
                                    padding: EdgeInsets.zero,
                                  ),
                                ),
                              if (bookmarkCount > 0)
                                Padding(
                                  padding: const EdgeInsets.only(left: 8),
                                  child: Badge(
                                    label: Text('$bookmarkCount'),
                                    child: const Icon(
                                      Icons.bookmark_border,
                                      size: 18,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                      subtitle: Text(
                        [
                          if (e.pairedCacheId.trim().isNotEmpty) '짝 논문 있음',
                          e.metaResumeLine(
                            resumeSection:
                                lib.progressResumeByCacheId.containsKey(e.id)
                                    ? (lib.progressResumeByCacheId[e.id] ?? "")
                                    : null,
                          ),
                          e.timingLine(
                            lastReadLeftAt:
                                lib.readLeftAtByCacheId[e.id] ?? '',
                          ),
                          lib.figureHydrateLabel(e.id),
                          lib.harmonizeResidualLabel(e.id),
                        ].where((s) => s.isNotEmpty).join('\n'),
                      ),
                      isThreeLine: true,
                      selected: _selecting && selected,
                      trailing: _selecting
                          ? null
                          : Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (lib.figureHydrateSnapshot(e.id)?.showFailure ==
                                    true)
                                  IconButton(
                                    icon: const Icon(Icons.refresh, size: 22),
                                    tooltip: '그림 다시 받기',
                                    onPressed: lib.opening ||
                                            lib.uploading ||
                                            lib.reanalyzing ||
                                            _deleting
                                        ? null
                                        : () => lib.enqueueFigureHydrate(
                                              e.id,
                                              force: true,
                                            ),
                                  ),
                                if (lib.figureHydrateSnapshot(e.id)?.showFailure ==
                                    true)
                                  IconButton(
                                    icon: const Icon(Icons.close, size: 20),
                                    tooltip: '알림 닫기',
                                    onPressed: () =>
                                        lib.dismissFigureHydrate(e.id),
                                  ),
                                if (lib.harmonizeResidualSnapshot(e.id)
                                        ?.showFailure ==
                                    true)
                                  IconButton(
                                    icon: const Icon(Icons.refresh, size: 22),
                                    tooltip: '재감수 다시',
                                    onPressed: lib.opening ||
                                            lib.uploading ||
                                            lib.reanalyzing ||
                                            _deleting
                                        ? null
                                        : () => lib.enqueueHarmonizeResidualPoll(
                                              e.id,
                                              force: true,
                                            ),
                                  ),
                                if (lib.harmonizeResidualSnapshot(e.id)
                                        ?.showFailure ==
                                    true)
                                  IconButton(
                                    icon: const Icon(Icons.close, size: 20),
                                    tooltip: '재감수 알림 닫기',
                                    onPressed: () =>
                                        lib.dismissHarmonizeResidual(e.id),
                                  ),
                                if (e.canMergeSupplementary)
                                  TextButton.icon(
                                    icon: const Icon(Icons.merge_type, size: 18),
                                    label: const Text('짝 합치기'),
                                    style: TextButton.styleFrom(
                                      visualDensity: VisualDensity.compact,
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                      ),
                                    ),
                                    onPressed: lib.opening ||
                                            lib.uploading ||
                                            lib.reanalyzing ||
                                            _deleting
                                        ? null
                                        : () => _mergeSupplementary(e),
                                  ),
                                if (e.retentionWarn)
                                  IconButton(
                                    icon: Icon(
                                      Icons.warning_amber_rounded,
                                      color: Theme.of(context)
                                          .colorScheme
                                          .tertiary,
                                      size: 22,
                                    ),
                                    tooltip: '보관 기한 임박',
                                    onPressed: lib.opening ||
                                            lib.uploading ||
                                            lib.reanalyzing ||
                                            _deleting
                                        ? null
                                        : () => _showRetentionSheet(e),
                                  ),
                              ],
                            ),
                      onTap: lib.opening ||
                              lib.uploading ||
                              lib.reanalyzing ||
                              _deleting
                          ? null
                          : () {
                              if (_selecting) {
                                _toggleSelected(e.id);
                              } else {
                                _open(e);
                              }
                            },
                      onLongPress: lib.opening ||
                              lib.uploading ||
                              lib.reanalyzing ||
                              _deleting
                          ? null
                          : () {
                              if (_selecting) {
                                _toggleSelected(e.id);
                              } else {
                                _enterEdit(e.id);
                              }
                            },
                    );
                    if (!_selecting) {
                      return KeyedSubtree(
                        key: ValueKey<String>(e.id),
                        child: tile,
                      );
                    }
                    return ReorderableDelayedDragStartListener(
                      key: ValueKey<String>(e.id),
                      index: i,
                      enabled: !lib.opening &&
                          !lib.uploading &&
                          !lib.reanalyzing &&
                          !_deleting,
                      child: tile,
                    );
                  },
                ),
            ],
          ),
        );
      },
    );
  }
}
