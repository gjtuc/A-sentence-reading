import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../api/paper_models.dart';
import '../state/auth_controller.dart';
import '../state/library_controller.dart';

/// Authenticated paper list → open · single PDF upload (design/62 · design/70).
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
      widget.library.clearAll();
    }
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
    if (lib.uploading || lib.opening) return;

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
        if (lib.loading && lib.papers.isEmpty && !lib.uploading) {
          return const Center(child: CircularProgressIndicator());
        }
        return RefreshIndicator(
          onRefresh: lib.uploading ? () async {} : lib.refresh,
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
                        onPressed: lib.loading || lib.opening || lib.uploading
                            ? null
                            : _pickAndUpload,
                        icon: const Icon(Icons.upload_file),
                        tooltip: 'PDF 가져오기',
                      ),
                      IconButton(
                        onPressed: lib.loading || lib.opening || lib.uploading
                            ? null
                            : lib.refresh,
                        icon: const Icon(Icons.refresh),
                        tooltip: '새로고침',
                      ),
                    ],
                  ),
                ),
              ),
              if (lib.uploading)
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
                                  ' · 끝나면 클라우드 보관함에 자동 저장'
                                ),
                          style: Theme.of(context).textTheme.bodySmall,
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
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      lib.error!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ),
                ),
              if (lib.papers.isEmpty && !lib.uploading)
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
                SliverList.builder(
                  itemCount: lib.papers.length,
                  itemBuilder: (context, i) {
                    final e = lib.papers[i];
                    return ListTile(
                      title: Text(e.title),
                      subtitle: Text(
                        [
                          e.subtitle,
                          if (e.updatedAt.isNotEmpty) e.updatedAt,
                        ].where((s) => s.isNotEmpty).join('\n'),
                      ),
                      isThreeLine: e.updatedAt.isNotEmpty,
                      trailing: lib.opening
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.chevron_right),
                      onTap: lib.opening || lib.uploading
                          ? null
                          : () => _open(e),
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
