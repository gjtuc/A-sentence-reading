import 'package:flutter/material.dart';

import '../api/client.dart';
import '../config.dart';

/// Probes Cloud Run `GET /api/status` so sideload builds can confirm API reachability.
class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});

  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> {
  late final AsrClient _client;
  Future<AsrStatus>? _future;

  @override
  void initState() {
    super.initState();
    _client = AsrClient();
    _future = _client.fetchStatus();
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _future = _client.fetchStatus();
    });
  }

  @override
  Widget build(BuildContext context) {
    final base = AsrConfig().effectiveBaseUrl;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('API: $base', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 12),
          Expanded(
            child: FutureBuilder<AsrStatus>(
              future: _future,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snap.hasError) {
                  return Center(
                    child: Text(
                      '연결 실패\n${snap.error}',
                      textAlign: TextAlign.center,
                    ),
                  );
                }
                final s = snap.data!;
                return ListView(
                  children: [
                    ListTile(title: const Text('ok'), subtitle: Text('${s.ok}')),
                    ListTile(title: const Text('version'), subtitle: Text(s.version)),
                    ListTile(title: const Text('pipeline'), subtitle: Text(s.pipeline)),
                    ListTile(
                      title: const Text('mobile_flutter_scaffold'),
                      subtitle: Text('${s.mobileFlutterScaffold}'),
                    ),
                  ],
                );
              },
            ),
          ),
          FilledButton(onPressed: _reload, child: const Text('다시 확인')),
        ],
      ),
    );
  }
}
