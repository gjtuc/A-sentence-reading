import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../api/library_reorder_proxy.dart';
import '../api/paper_models.dart';
import '../state/auth_controller.dart';
import '../state/library_controller.dart';

/// Authenticated paper list → open · single PDF upload (design/62 · design/70 · design/122).
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({
    super.key,
    required this.auth,
    required this.library,
    this.onOpened,
  });

  final AuthController auth;
  final LibraryController library;

  /// Called after a successful open (e.g. jump to Reader tab).
  final VoidCallback? onOpened;

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  /// design/102 — trash toggles multi-select delete mode.
  bool _selecting = false;
  final Set<String> _selected = <String>{};
  bool _deleting = false;

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

  void _toggleSelecting() {
    setState(() {
      _selecting = !_selecting;
      if (!_selecting) _selected.clear();
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

  Future<void> _confirmDelete() async {
    if (_deleting || _selected.isEmpty) return;
    final count = _selected.length;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('보관본 삭제'),
        content: Text(
          '선택한 $count건을 삭제할까요?\n'
          '클라우드(GCS) 문서와 노트·북마크·연습 기록도 함께 지워집니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _deleting = true);
    final ids = _selected.toList(growable: false);
    final deleted = await widget.library.deletePapers(ids);
    if (!mounted) return;
    setState(() {
      _deleting = false;
      _selecting = false;
      _selected.clear();
    });
    final msg = deleted == 0
        ? (widget.library.error ?? '삭제에 실패했습니다.')
        : deleted == ids.length
            ? '$deleted건을 삭제했습니다.'
            : '$deleted/${ids.length}건을 삭제했습니다.';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
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

  Future<void> _reanalyze(PaperEntry entry) async {
    if (!entry.hasSource) return;
    final ok = await widget.library.reanalyzePaper(entry);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok
              ? '재분석이 완료되었습니다.'
              : (widget.library.error ?? '재분석에 실패했습니다.'),
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
    final hint = widget.library.uploadBackgroundHint;
    if (hint != null && hint.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
    }
    if (result == null) return;
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

  Future<void> _pickAndUpload() async {
    final lib = widget.library;
    if (lib.uploading || lib.reanalyzing || lib.opening) return;

    // WHY: single-file chip — multi-select deferred (design/70).
    // design/71: same content_hash re-pick auto-reattaches inside uploadPdf.
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf'],
      allowMultiple: false,
      withData: true,
    );
    if (!mounted) return;
    if (picked == null || picked.files.isEmpty) {
      // EDGE: user cancelled — stay silent (not a failure snackbar).
      return;
    }
    final f = picked.files.first;
    final name = f.name.trim();
    final bytes = f.bytes;
    if (name.isEmpty || bytes == null || bytes.isEmpty) {
      // EDGE: some SAF providers omit bytes — fail-closed, no fake success.
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('파일을 읽지 못했습니다. 다른 PDF를 골라 주세요.')),
      );
      return;
    }

    // WHY: ingest already writes user GCS papers — cloud library is mandatory, not a
    // second "PDF 올리기" step after processing (design/70).
    final result = await lib.uploadPdf(filename: name, bytes: bytes);
    if (!mounted) return;
    // design/74 · product 3A: permission denied → upload still ran; warn once.
    final hint = lib.uploadBackgroundHint;
    if (hint != null && hint.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
    }
    if (result == null) {
      final msg = lib.error ?? '처리에 실패했습니다.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      return;
    }
    PaperEntry? entry;
    for (final p in lib.papers) {
      if (p.id == result.cacheId) {
        entry = p;
        break;
      }
    }
    if (entry == null) {
      // EDGE: should be unreachable after uploadPdf list check — fail-closed.
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('보관함에서 논문을 찾지 못했습니다.')),
      );
      return;
    }
    // Auto-open: user must not tap the paper (or PDF 올리기 again) to finish.
    await _open(entry);
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([widget.auth, widget.library]),
      builder: (context, _) {
        if (!widget.auth.isLoggedIn) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                '보관 목록을 보려면 먼저 로그인하세요.\n(이메일 로그인 · 하단 계정 탭)',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        final lib = widget.library;
        if (lib.loading && lib.papers.isEmpty && !lib.uploading && !lib.reanalyzing) {
          return const Center(child: CircularProgressIndicator());
        }
        return RefreshIndicator(
          onRefresh: (lib.uploading || lib.reanalyzing) ? () async {} : lib.refresh,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          '보관 ${lib.papers.length}건',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      IconButton(
                        onPressed: lib.loading ||
                                lib.opening ||
                                lib.uploading ||
                                lib.reanalyzing ||
                                _deleting ||
                                lib.papers.isEmpty
                            ? null
                            : _toggleSelecting,
                        icon: Icon(
                          _selecting ? Icons.close : Icons.delete_outline,
                        ),
                        tooltip: _selecting ? '선택 취소' : '삭제',
                      ),
                      IconButton(
                        onPressed: lib.loading ||
                                lib.opening ||
                                lib.uploading ||
                                lib.reanalyzing ||
                                _deleting
                            ? null
                            : _pickAndUpload,
                        icon: const Icon(Icons.upload_file),
                        tooltip: 'PDF 가져오기',
                      ),
                      IconButton(
                        onPressed: lib.loading ||
                                lib.opening ||
                                lib.uploading ||
                                lib.reanalyzing ||
                                _deleting
                            ? null
                            : lib.refresh,
                        icon: const Icon(Icons.refresh),
                        tooltip: '새로고침',
                      ),
                    ],
                  ),
                ),
              ),
              if (_selecting)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            _selected.isEmpty
                                ? '삭제할 문서를 선택하세요.'
                                : '${_selected.length}건 선택됨',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                        FilledButton.tonalIcon(
                          onPressed: _deleting || _selected.isEmpty
                              ? null
                              : _confirmDelete,
                          icon: _deleting
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.delete),
                          label: const Text('삭제'),
                        ),
                      ],
                    ),
                  ),
                )
              else if (!lib.uploading && !lib.reanalyzing)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      '이름을 길게 누른 뒤 끌어 순서를 바꿀 수 있습니다.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ),
              if (lib.reanalyzing)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        LinearProgressIndicator(
                          value: lib.uploadPercent > 0
                              ? (lib.uploadPercent.clamp(0, 100) / 100.0)
                              : null,
                        ),
                        const SizedBox(height: 6),
                        Text(
                          '재분석 중 ${lib.uploadPercent}%'
                          '${lib.uploadStage.isEmpty ? '' : ' · ${lib.uploadStage}'}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                )
              else if (lib.uploading)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        LinearProgressIndicator(
                          // EDGE (design/75): stalled → do not animate fake progress.
                          value: lib.uploadStalled
                              ? 0
                              : (lib.uploadPercent > 0
                                  ? (lib.uploadPercent.clamp(0, 100) / 100.0)
                                  : null),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          lib.uploadStalled
                              ? (lib.uploadStage.isEmpty
                                  ? '중단됨 · 앱을 열면 이어갑니다'
                                  : lib.uploadStage)
                              : (
                                  // WHY: cloud archive is part of processing — not a separate upload tap.
                                  '처리 중 ${lib.uploadPercent}%'
                                  '${lib.uploadStage.isEmpty ? '' : ' · ${lib.uploadStage}'}'
                                  ' · 클라우드 보관함에 자동 저장'
                                ),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        const SizedBox(height: 8),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton(
                            // design/132 — early cancel; late stage may refuse on server.
                            onPressed: () => lib.cancelUpload(),
                            child: const Text('취소'),
                          ),
                        ),
                        if (lib.uploadBatteryHint != null) ...[
                          const SizedBox(height: 8),
                          Text(
                            lib.uploadBatteryHint!,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 4),
                          Wrap(
                            spacing: 8,
                            children: [
                              TextButton(
                                onPressed: () async {
                                  await lib.openBatterySettings();
                                },
                                child: const Text('배터리 설정'),
                              ),
                              TextButton(
                                onPressed: () => lib.dismissBatteryHint(),
                                child: const Text('나중에'),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
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
                            'PDF를 고르면 처리가 끝난 뒤\n'
                            '클라우드 보관함에 자동으로 저장됩니다.',
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 16),
                          FilledButton.tonalIcon(
                            onPressed: lib.loading ? null : _pickAndUpload,
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
                  proxyDecorator: (child, index, animation) {
                    final scheme = Theme.of(context).colorScheme;
                    return libraryReorderProxyDecorator(
                      child,
                      index,
                      animation,
                      colorScheme: scheme,
                    );
                  },
                  onReorder: (oldIndex, newIndex) {
                    if (_selecting ||
                        lib.opening ||
                        lib.uploading ||
                        lib.reanalyzing ||
                        _deleting) {
                      return;
                    }
                    // WHY: save path unchanged this chip (product 4A).
                    unawaited(lib.reorderPapers(oldIndex, newIndex));
                  },
                  itemBuilder: (context, i) {
                    final e = lib.papers[i];
                    final selected = _selected.contains(e.id);
                    final tile = ListTile(
                      leading: _selecting
                          ? Checkbox(
                              value: selected,
                              onChanged: _deleting
                                  ? null
                                  : (_) => _toggleSelected(e.id),
                            )
                          : null,
                      title: Row(
                        children: [
                          Expanded(child: Text(e.title)),
                          if (e.libraryTag.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(left: 8),
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
                        ],
                      ),
                      subtitle: Text(
                        [
                          e.subtitle,
                          if (e.updatedAt.isNotEmpty) e.updatedAt,
                        ].where((s) => s.isNotEmpty).join('\n'),
                      ),
                      isThreeLine: e.updatedAt.isNotEmpty,
                      selected: _selecting && selected,
                      trailing: _selecting
                          ? null
                          : Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (e.canMergeSupplementary)
                                  IconButton(
                                    icon: const Icon(Icons.merge_type, size: 22),
                                    tooltip: '보충자료 합치기',
                                    onPressed: lib.opening ||
                                            lib.uploading ||
                                            lib.reanalyzing ||
                                            _deleting
                                        ? null
                                        : () => _mergeSupplementary(e),
                                  ),
                                if (e.hasSource)
                                  IconButton(
                                    icon: Icon(
                                      Icons.autorenew,
                                      size: 22,
                                      color: lib.reanalyzing &&
                                              lib.reanalyzingCacheId == e.id
                                          ? Theme.of(context)
                                              .colorScheme
                                              .primary
                                          : null,
                                    ),
                                    tooltip: '재분석',
                                    onPressed: lib.opening ||
                                            lib.uploading ||
                                            lib.reanalyzing ||
                                            _deleting
                                        ? null
                                        : () => _reanalyze(e),
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
                                if (lib.opening ||
                                    (lib.reanalyzing &&
                                        lib.reanalyzingCacheId == e.id))
                                  const SizedBox(
                                    width: 24,
                                    height: 24,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                else
                                  const Icon(Icons.drag_handle),
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
                    if (_selecting) {
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
