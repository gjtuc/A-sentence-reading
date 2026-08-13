/// design/130 — admin error log list (settings entry).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';

class ErrorLogsScreen extends StatefulWidget {
  const ErrorLogsScreen({super.key, required this.client});

  final AsrClient client;

  @override
  State<ErrorLogsScreen> createState() => _ErrorLogsScreenState();
}

class _ErrorLogsScreenState extends State<ErrorLogsScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _reload(markSeen: true);
  }

  void _reload({bool markSeen = false}) {
    setState(() {
      _future = () async {
        if (markSeen) {
          try {
            await widget.client.markAdminErrorsSeen();
          } catch (_) {
            // EDGE: still show list even if seen fails.
          }
        }
        return widget.client.fetchAdminErrorLogs(limit: 80);
      }();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('오류 로그'),
        actions: [
          IconButton(
            tooltip: '새로고침',
            onPressed: () => _reload(markSeen: false),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            // WHY: do not show internal route paths (errors/admin) to admins as raw.
            // FAIL-CLOSED: still an explicit failure — never an empty "성공" list.
            const msg = '오류 로그를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(msg, textAlign: TextAlign.center),
              ),
            );
          }
          final items = snap.data ?? const [];
          if (items.isEmpty) {
            return const Center(child: Text('아직 수집된 오류가 없습니다.'));
          }
          return ListView.separated(
            padding: const EdgeInsets.all(12),
            itemCount: items.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, i) {
              final e = items[i];
              final kind = '${e['kind'] ?? ''}';
              final ts = '${e['ts'] ?? ''}';
              final title = '${e['paper_title'] ?? ''}';
              final cid = '${e['cache_id'] ?? ''}';
              final email = '${e['email'] ?? ''}';
              final msg = '${e['message'] ?? ''}';
              final stage = '${e['stage'] ?? ''}';
              return ListTile(
                isThreeLine: true,
                title: Text(
                  '$kind · $ts',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                subtitle: Text(
                  [
                    if (email.isNotEmpty) email,
                    if (title.isNotEmpty) title,
                    if (cid.isNotEmpty) 'cache:$cid',
                    if (stage.isNotEmpty) 'stage:$stage',
                    msg,
                  ].join('\n'),
                  maxLines: 8,
                  overflow: TextOverflow.ellipsis,
                ),
                onTap: () {
                  showDialog<void>(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: Text(kind),
                      content: SingleChildScrollView(
                        child: SelectableText(
                          [
                            ts,
                            if (email.isNotEmpty) 'email: $email',
                            if (title.isNotEmpty) 'paper: $title',
                            if (cid.isNotEmpty) 'cache_id: $cid',
                            if (stage.isNotEmpty) 'stage: $stage',
                            '',
                            msg,
                            '',
                            '${e['stack'] ?? ''}',
                          ].join('\n'),
                        ),
                      ),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(ctx),
                          child: const Text('닫기'),
                        ),
                      ],
                    ),
                  );
                },
              );
            },
          );
        },
      ),
    );
  }
}
