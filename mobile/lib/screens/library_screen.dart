import 'package:flutter/material.dart';

import '../state/auth_controller.dart';
import '../state/library_controller.dart';

/// Authenticated paper list → open (design/62).
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
        widget.library.refresh();
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
      widget.library.refresh();
    } else {
      widget.library.clearAll();
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
        if (lib.loading && lib.papers.isEmpty) {
          return const Center(child: CircularProgressIndicator());
        }
        return RefreshIndicator(
          onRefresh: lib.refresh,
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
                        onPressed: lib.loading || lib.opening ? null : lib.refresh,
                        icon: const Icon(Icons.refresh),
                        tooltip: '새로고침',
                      ),
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
              if (lib.papers.isEmpty)
                const SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        '아직 보관한 논문이 없습니다.\n'
                        'PC 웹에서 PDF를 업로드하면 여기에 나타납니다.\n'
                        '(앱 업로드는 후속)',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                )
              else
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
                      onTap: lib.opening ? null : () => _open(e),
                    );
                  },
                ),
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'Live Enable / IPS: Trading Gate · ASR 밖',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12),
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
