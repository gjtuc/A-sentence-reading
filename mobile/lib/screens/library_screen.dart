import 'dart:async';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/ingest_models.dart';
import '../api/paper_models.dart';
import '../state/annotation_controller.dart';
import '../state/auth_controller.dart';
import '../state/bookmark_controller.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../widgets/library_card_hold.dart';
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
  /// design/224 — trash only while editing. design/308 — hold popup, then drag.
  bool _selecting = false;
  final Set<String> _selected = <String>{};
  bool _deleting = false;
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _itemKeys = <String, GlobalKey>{};
  OverlayEntry? _menuEntry;
  OverlayEntry? _dragEntry;
  Timer? _edgeScrollTimer;
  bool _dragging = false;
  Offset _dragGlobal = Offset.zero;
  List<String> _movingIds = const <String>[];
  int? _dropIndex;

  bool get _gestureBlocked =>
      _deleting ||
      widget.library.opening ||
      widget.library.uploading ||
      widget.library.reanalyzing;

  GlobalKey _itemKey(String id) => _itemKeys.putIfAbsent(id, GlobalKey.new);

  void _dismissMenu() {
    _menuEntry?.remove();
    _menuEntry = null;
  }

  void _dismissDragOverlay() {
    _edgeScrollTimer?.cancel();
    _edgeScrollTimer = null;
    _dragEntry?.remove();
    _dragEntry = null;
  }

  void _endDrag() {
    _dismissDragOverlay();
    if (!mounted) {
      _dragging = false;
      _movingIds = const <String>[];
      _dropIndex = null;
      return;
    }
    if (!_dragging && _dropIndex == null && _movingIds.isEmpty) return;
    setState(() {
      _dragging = false;
      _movingIds = const <String>[];
      _dropIndex = null;
    });
  }

  void _selectFromMenu(String id) {
    setState(() {
      _selecting = true;
      _selected.add(id);
    });
  }

  void _showMenu(String id, Offset global) {
    _dismissMenu();
    final overlay = Overlay.maybeOf(context);
    if (overlay == null) return;
    _menuEntry = OverlayEntry(
      builder: (ctx) {
        final size = MediaQuery.sizeOf(ctx);
        final top = (global.dy - 96).clamp(72.0, size.height - 160);
        return Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                onTap: _dismissMenu,
                behavior: HitTestBehavior.opaque,
              ),
            ),
            Positioned(
              left: 20,
              top: top,
              child: Material(
                elevation: 8,
                borderRadius: BorderRadius.circular(12),
                color: Theme.of(ctx).colorScheme.surfaceContainerHigh,
                child: IntrinsicWidth(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      ListTile(
                        dense: true,
                        leading: const Icon(Icons.delete_outline),
                        title: const Text('삭제'),
                        onTap: () {
                          _dismissMenu();
                          unawaited(_softHideWithUndo([id]));
                        },
                      ),
                      ListTile(
                        dense: true,
                        leading: const Icon(Icons.check_box_outlined),
                        title: const Text('선택'),
                        onTap: () {
                          _dismissMenu();
                          _selectFromMenu(id);
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
    overlay.insert(_menuEntry!);
  }

  int _insertIndexFor(Offset global) {
    final papers = widget.library.papers;
    for (var i = 0; i < papers.length; i++) {
      final ctx = _itemKeys[papers[i].id]?.currentContext;
      if (ctx == null) continue;
      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null || !box.hasSize) continue;
      final mid = box.localToGlobal(Offset.zero).dy + box.size.height / 2;
      if (global.dy < mid) return i;
    }
    return papers.length;
  }

  void _applyEdgeScroll(Offset global) {
    if (!_scroll.hasClients || !mounted) return;
    final box = context.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    final dy = box.globalToLocal(global).dy;
    const edge = 80.0;
    var delta = 0.0;
    if (dy < edge) {
      delta = -18;
    } else if (dy > box.size.height - edge) {
      delta = 18;
    }
    if (delta == 0) return;
    final pos = _scroll.position;
    final target = (_scroll.offset + delta).clamp(
      pos.minScrollExtent,
      pos.maxScrollExtent,
    );
    if (target != _scroll.offset) _scroll.jumpTo(target);
  }

  void _onCardHold(String id, Offset global) {
    if (!mounted || _gestureBlocked) return;
    HapticFeedback.mediumImpact();
    if (_selecting && _selected.contains(id)) return;
    _showMenu(id, global);
  }

  void _onCardDragStart(String id, Offset global) {
    if (!mounted || _gestureBlocked) return;
    _dismissMenu();
    final papers = widget.library.papers;
    final moving = (_selecting && _selected.contains(id) && _selected.length > 1)
        ? <String>[
            for (final p in papers)
              if (_selected.contains(p.id)) p.id,
          ]
        : <String>[id];
    setState(() {
      _dragging = true;
      _movingIds = moving;
      _dragGlobal = global;
      _dropIndex = _insertIndexFor(global);
    });
    final overlay = Overlay.maybeOf(context);
    if (overlay != null) {
      _dragEntry = OverlayEntry(
        builder: (ctx) {
          final title = _dragTitle();
          final n = _movingIds.length;
          final top = (_dragGlobal.dy - 28).clamp(
            8.0,
            MediaQuery.sizeOf(ctx).height - 64,
          );
          return Positioned(
            left: 16,
            right: 16,
            top: top,
            child: IgnorePointer(
              child: Material(
                elevation: 8,
                borderRadius: BorderRadius.circular(12),
                color: Theme.of(ctx).colorScheme.surfaceContainerHigh,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
                  child: Text(
                    n > 1 ? '$title 외 ${n - 1}건' : title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
            ),
          );
        },
      );
      overlay.insert(_dragEntry!);
    }
    _edgeScrollTimer?.cancel();
    _edgeScrollTimer = Timer.periodic(const Duration(milliseconds: 50), (_) {
      if (!_dragging || !mounted) return;
      _applyEdgeScroll(_dragGlobal);
      final next = _insertIndexFor(_dragGlobal);
      if (next != _dropIndex) {
        setState(() => _dropIndex = next);
      }
    });
    HapticFeedback.mediumImpact();
  }

  String _dragTitle() {
    final id = _movingIds.isEmpty ? '' : _movingIds.first;
    for (final p in widget.library.papers) {
      if (p.id == id) return p.title;
    }
    return '선택한 논문';
  }

  void _onCardDragUpdate(Offset global) {
    if (!_dragging) return;
    _dragGlobal = global;
    final next = _insertIndexFor(global);
    if (next != _dropIndex && mounted) {
      setState(() => _dropIndex = next);
    } else {
      _dragEntry?.markNeedsBuild();
    }
    _applyEdgeScroll(global);
  }

  void _onCardDragEnd(Offset global) {
    final moving = List<String>.from(_movingIds);
    final insertAt = _insertIndexFor(global);
    _endDrag();
    if (moving.isEmpty || _gestureBlocked) return;
    unawaited(widget.library.reorderPaperBlock(moving, insertAt));
  }

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
      unawaited(widget.library.reloadResumeLabels());
    });
  }

  @override
  void dispose() {
    _dismissMenu();
    _dismissDragOverlay();
    _scroll.dispose();
    widget.auth.removeListener(_onAuth);
    super.dispose();
  }

  void _onAuth() {
    if (widget.auth.isLoggedIn) {
      _loadAndResume();
    } else {
      // WHY (MULTI-USER): wipe list + upload draft so next account cannot resume.
      _dismissMenu();
      _dismissDragOverlay();
      _dragging = false;
      _movingIds = const <String>[];
      setState(() {
        _selecting = false;
        _selected.clear();
      });
      widget.library.clearAll();
    }
  }

  void _exitEdit() {
    _dismissMenu();
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
  /// design/258 — live seconds countdown; dismiss when purge fires.
  /// design/278 — undo uses expanded hiddenIds (mate soft-hide).
  Future<void> _softHideWithUndo(List<String> ids) async {
    if (_deleting || ids.isEmpty) return;
    setState(() => _deleting = true);
    final result = await widget.library.softHidePapers(ids);
    if (!mounted) return;
    final undoIds = result.hiddenIds.isNotEmpty
        ? result.hiddenIds
        : ids;
    setState(() {
      _deleting = false;
      for (final id in undoIds) {
        _selected.remove(id);
      }
      if (_selected.isEmpty) {
        _selecting = false;
      }
    });
    if (result.hidden == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(widget.library.error ?? '숨기기에 실패했습니다.'),
        ),
      );
      return;
    }
    final purgeAt = result.purgeAtMs ??
        DateTime.now().millisecondsSinceEpoch +
            const Duration(seconds: 60).inMilliseconds;
    final remainMs =
        (purgeAt - DateTime.now().millisecondsSinceEpoch).clamp(0, 120000);
    ScaffoldMessenger.of(context).clearSnackBars();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        // Keep alive until countdown hits 0; content dismisses itself.
        duration: Duration(milliseconds: remainMs + 1500),
        content: _SoftHideCountdownContent(
          hidden: result.hidden,
          purgeAtMs: purgeAt,
          onExpired: () {
            if (!mounted) return;
            ScaffoldMessenger.of(context).hideCurrentSnackBar();
            unawaited(widget.library.purgeDueSoftDeletes());
          },
        ),
        action: SnackBarAction(
          label: '실행 취소',
          onPressed: () {
            unawaited(widget.library.undoSoftHide(undoIds));
          },
        ),
      ),
    );
  }

  Future<void> _confirmDelete() async {
    if (_deleting || _selected.isEmpty) return;
    await _softHideWithUndo(_selected.toList(growable: false));
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
          child: NotificationListener<ScrollNotification>(
            onNotification: (n) {
              if (n is ScrollUpdateNotification && _menuEntry != null && !_dragging) {
                _dismissMenu();
              }
              return false;
            },
            child: CustomScrollView(
            controller: _scroll,
            physics: _dragging
                ? const NeverScrollableScrollPhysics()
                : const AlwaysScrollableScrollPhysics(),
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
                              : const Icon(Icons.delete_outline),
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
                        tooltip: '논문 가져오기',
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
                      '체크한 논문을 길게 눌러 한 덩어리로 옮깁니다. 휴지통은 숨기기.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                )
              else if (!lib.uploading && !lib.reanalyzing)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      '길게 누르면 삭제·선택 · 손을 떼지 않고 끌면 순서를 바꿉니다.',
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
                            label: const Text('논문 가져오기'),
                          ),
                        ],
                      ),
                    ),
                  ),
                )
              else if (lib.papers.isNotEmpty)
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                  (context, i) {
                    final e = lib.papers[i];
                    final selected = _selected.contains(e.id);
                    final bookmarkCount = widget.bookmarks.paperBookmarkCount(e.id);
                    final dim = _dragging && _movingIds.contains(e.id);
                    final showLine = _dragging && _dropIndex == i;
                    final tile = ListTile(
                      leading: _selecting
                          ? Checkbox(
                              value: selected,
                              onChanged: _deleting
                                  ? null
                                  : (_) => _toggleSelected(e.id),
                            )
                          : (e.pairedCacheId.trim().isNotEmpty
                              ? Container(
                                  width: 10,
                                  alignment: Alignment.center,
                                  child: Container(
                                    width: 3,
                                    height: 36,
                                    decoration: BoxDecoration(
                                      color: Theme.of(context)
                                          .colorScheme
                                          .primary
                                          .withValues(alpha: 0.55),
                                      borderRadius: BorderRadius.circular(2),
                                    ),
                                  ),
                                )
                              : null),
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
                          if (e.pairedCacheId.trim().isNotEmpty)
                            '⇄ 짝 있음 · 합치면 한 세션으로 읽기',
                          e.metaLine(),
                          e.progressResumeLine(
                            readSection: lib.progressResumeByCacheId[e.id],
                            practiceSection: lib.practiceResumeByCacheId[e.id],
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
                                    label: const Text('짝과 합치기'),
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
                    );
                    return KeyedSubtree(
                      key: ValueKey<String>(e.id),
                      child: Opacity(
                        opacity: dim ? 0.35 : 1,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (showLine)
                              Container(
                                height: 3,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                            LibraryCardHold(
                              key: _itemKey(e.id),
                              enabled: !_gestureBlocked,
                              onHold: (pos) => _onCardHold(e.id, pos),
                              onDragStart: (pos) => _onCardDragStart(e.id, pos),
                              onDragUpdate: _onCardDragUpdate,
                              onDragEnd: _onCardDragEnd,
                              onCancel: _endDrag,
                              child: tile,
                            ),
                            if (_dragging &&
                                _dropIndex == lib.papers.length &&
                                i == lib.papers.length - 1)
                              Container(
                                height: 3,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                  childCount: lib.papers.length,
                  ),
                ),
            ],
          ),
          ),
        );
      },
    );
  }
}

/// design/258 — live soft-hide countdown inside SnackBar content.
class _SoftHideCountdownContent extends StatefulWidget {
  const _SoftHideCountdownContent({
    required this.hidden,
    required this.purgeAtMs,
    required this.onExpired,
  });

  final int hidden;
  final int purgeAtMs;
  final VoidCallback onExpired;

  @override
  State<_SoftHideCountdownContent> createState() =>
      _SoftHideCountdownContentState();
}

class _SoftHideCountdownContentState extends State<_SoftHideCountdownContent> {
  Timer? _timer;
  int _secsLeft = 60;
  bool _expired = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _refresh() {
    if (_expired) return;
    final leftMs = widget.purgeAtMs - DateTime.now().millisecondsSinceEpoch;
    final secs = (leftMs / 1000).ceil();
    if (secs <= 0) {
      _expired = true;
      _timer?.cancel();
      widget.onExpired();
      return;
    }
    if (!mounted) return;
    if (secs != _secsLeft) {
      setState(() => _secsLeft = secs);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Text('${widget.hidden}건을 숨겼습니다.\n$_secsLeft초 후 영구 삭제됩니다.');
  }
}
