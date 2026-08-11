/// Waiting-only shell when logged in but invite not approved (design/84).
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/access_models.dart';
import '../api/client.dart';
import '../state/auth_controller.dart';

/// Invite redeem + pending/denied copy. Polls until [AccessStatus.canUsePaid].
class AccessWaitingScreen extends StatefulWidget {
  const AccessWaitingScreen({
    super.key,
    required this.auth,
    required this.onUnlocked,
  });

  final AuthController auth;
  final VoidCallback onUnlocked;

  @override
  State<AccessWaitingScreen> createState() => _AccessWaitingScreenState();
}

class _AccessWaitingScreenState extends State<AccessWaitingScreen> {
  final _code = TextEditingController();
  AccessStatus? _access;
  String? _error;
  bool _busy = false;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
    // WHY: admin Allow on another device/instance — auto enter without tap.
    _poll = Timer.periodic(const Duration(seconds: 5), (_) {
      unawaited(_reload(silent: true));
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    _code.dispose();
    super.dispose();
  }

  Future<void> _reload({bool silent = false}) async {
    if (!widget.auth.isLoggedIn) return;
    if (!silent) {
      setState(() {
        _busy = true;
        _error = null;
      });
    }
    try {
      final st = await widget.auth.client.fetchAccessStatus();
      if (!mounted) return;
      setState(() => _access = st);
      // EDGE: gate off or admin/allowed → leave waiting shell.
      if (!st.gateEnabled || st.canUsePaid) {
        widget.onUnlocked();
      }
    } on AsrApiException catch (e) {
      if (!mounted) return;
      // FAIL-CLOSED: do not unlock on error (would open paid UI empty-success).
      if (!silent) setState(() => _error = e.message);
    } catch (e) {
      if (!mounted) return;
      if (!silent) setState(() => _error = e.toString());
    } finally {
      if (mounted && !silent) setState(() => _busy = false);
    }
  }

  Future<void> _redeem() async {
    final raw = _code.text;
    if (!isPlausibleInviteCode(raw)) {
      setState(() => _error = '초대 코드 형식이 올바르지 않습니다.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final st = await widget.auth.client.redeemInviteCode(raw);
      if (!mounted) return;
      setState(() => _access = st);
      _code.clear();
      if (!st.gateEnabled || st.canUsePaid) {
        widget.onUnlocked();
      }
    } on AsrApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _hint(AccessStatus? a) {
    if (a == null) {
      return '초대 코드를 입력하면 관리자 승인 대기가 됩니다.';
    }
    if (a.isPending) {
      return '코드가 확인되었습니다. 관리자 승인을 기다리는 중입니다.';
    }
    if (a.isDenied) {
      // Product: deny == waiting — allow re-enter.
      return '승인이 거절되었습니다. 새 초대 코드를 다시 입력할 수 있습니다.';
    }
    return '초대 코드를 입력하면 관리자 승인 대기가 됩니다.';
  }

  @override
  Widget build(BuildContext context) {
    final a = _access;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('액세스 승인 대기', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 12),
              Text(_hint(a), style: Theme.of(context).textTheme.bodyMedium),
              if (a != null) ...[
                const SizedBox(height: 8),
                Text(
                  '상태: ${a.status}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              const SizedBox(height: 20),
              TextField(
                controller: _code,
                enabled: !_busy,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: '초대 코드',
                  border: OutlineInputBorder(),
                ),
                onSubmitted: (_) => _busy ? null : _redeem(),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _busy ? null : _redeem,
                child: const Text('코드 제출'),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: _busy ? null : () => unawaited(_reload()),
                child: const Text('상태 새로고침'),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              if (_busy) ...[
                const SizedBox(height: 16),
                const LinearProgressIndicator(),
              ],
              const Spacer(),
              TextButton(
                onPressed: _busy
                    ? null
                    : () async {
                        await widget.auth.logout();
                      },
                child: const Text('로그아웃'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
