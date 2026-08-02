import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/access_models.dart';
import '../api/client.dart';
import '../api/theme_models.dart';
import '../state/auth_controller.dart';
import '../state/theme_controller.dart';
import 'status_screen.dart';

/// Settings: account · theme · access gate · admin server probe (design/66–68).
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.theme,
    required this.auth,
  });

  final ThemeController theme;
  final AuthController auth;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _code = TextEditingController();
  AccessStatus? _access;
  List<Map<String, dynamic>> _pending = const [];
  List<Map<String, dynamic>> _events = const [];
  bool _loading = false;
  /// WHY separate from _loading: refresh must not disable Allow/Deny.
  /// EDGE: uiautomator/user tap during reload was ignored → invitee stayed pending.
  bool _mutating = false;
  String? _error;
  String? _minted;

  @override
  void initState() {
    super.initState();
    // WHY: session restore is async — first _reload often runs while logged out.
    // EDGE: without this listener, invite form appears after login but access/is_admin stay null
    // (admin mint chrome never shows even when ASR_ADMIN_EMAILS matches).
    widget.auth.addListener(_onAuthChanged);
    _reload();
  }

  void _onAuthChanged() {
    if (!mounted) return;
    // Re-fetch access when login/logout flips.
    _reload();
  }

  @override
  void dispose() {
    widget.auth.removeListener(_onAuthChanged);
    _code.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    if (!widget.auth.isLoggedIn) {
      // WHY: Settings may stay mounted across logout (IndexedStack / tab).
      // EDGE: leftover _minted OTP or typed invite must not appear for the next account.
      setState(() {
        _access = null;
        _pending = const [];
        _events = const [];
        _minted = null;
        _error = null;
        _code.clear();
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final st = await widget.auth.client.fetchAccessStatus();
      List<Map<String, dynamic>> pending = const [];
      List<Map<String, dynamic>> events = const [];
      // Admin endpoints 403 for non-admins — ignore.
      try {
        pending = await widget.auth.client.fetchAccessPending();
        events = await widget.auth.client.fetchAccessNotifications();
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _access = st;
        _pending = pending;
        _events = events.reversed.take(20).toList();
      });
    } on AsrApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _redeem() async {
    final raw = _code.text;
    if (!isPlausibleInviteCode(raw)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('초대 코드 형식이 올바르지 않습니다.')),
      );
      return;
    }
    setState(() => _loading = true);
    try {
      final st = await widget.auth.client.redeemInviteCode(raw);
      if (!mounted) return;
      setState(() => _access = st);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            st.isPending
                ? '코드 확인됨. 관리자 승인 대기 중.'
                : '상태: ${st.status}',
          ),
        ),
      );
      await _reload();
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _mint() async {
    setState(() => _loading = true);
    try {
      final code = await widget.auth.client.mintInviteCode();
      if (!mounted) return;
      setState(() => _minted = code);
      await Clipboard.setData(ClipboardData(text: code));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('발급됨·클립보드 복사: $code')),
      );
      await _reload();
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _decide(String uid, String decision) async {
    // WHY _mutating not _loading: admin may tap Allow while pending list refresh runs.
    setState(() => _mutating = true);
    try {
      await widget.auth.client.decideAccess(uid: uid, decision: decision);
      await _reload();
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _mutating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([widget.theme, widget.auth]),
      builder: (context, _) {
        if (!widget.theme.ready) {
          return const Center(child: CircularProgressIndicator());
        }
        final logged = widget.auth.isLoggedIn;
        final access = _access;
        final user = widget.auth.user;
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Text('설정', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            // WHY: account tab removed — login identity + logout live here (design/68).
            Text('계정', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (!logged || user == null)
              const Text('로그인이 필요합니다.')
            else ...[
              Text(user.displayLabel),
              if (user.providers.isNotEmpty)
                Text(
                  user.providers.join(', '),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: widget.auth.busy
                    ? null
                    : () => widget.auth.logout(),
                child: widget.auth.busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('로그아웃'),
              ),
            ],
            // WHY: admin-only nested page — keeps Settings short (design/68).
            // EDGE: non-admin must not see server flag dump.
            if (access?.isAdmin == true) ...[
              const SizedBox(height: 8),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.cloud_outlined),
                title: const Text('서버'),
                subtitle: const Text('연결 상태 확인'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => Scaffold(
                        appBar: AppBar(title: const Text('서버')),
                        body: const StatusScreen(),
                      ),
                    ),
                  );
                },
              ),
            ],
            const Divider(height: 32),
            Text('테마', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(
                  value: ThemeMode.system,
                  label: Text('시스템'),
                  icon: Icon(Icons.brightness_auto),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  label: Text('밝음'),
                  icon: Icon(Icons.light_mode),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  label: Text('어둠'),
                  icon: Icon(Icons.dark_mode),
                ),
              ],
              selected: {widget.theme.mode},
              onSelectionChanged: (set) {
                if (set.isEmpty) return;
                widget.theme.setMode(set.first);
              },
            ),
            const SizedBox(height: 8),
            Text('현재: ${themeModeLabelKo(widget.theme.mode)}'),
            const Divider(height: 32),
            Text('액세스 (초대 코드)', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              '관리자에게 부여받은 OTP를 입력하면 승인 대기가 됩니다.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (!logged) ...[
              const SizedBox(height: 12),
              const Text('로그인 후 초대 코드를 입력할 수 있습니다.'),
            ] else ...[
              const SizedBox(height: 12),
              if (_loading) const LinearProgressIndicator(),
              if (access != null)
                Text(
                  '상태: ${access.status}'
                  '${access.gateEnabled ? '' : ' (게이트 꺼짐)'}'
                  '${access.canUsePaid ? ' · 유료 API 가능' : ' · 유료 API 차단'}',
                ),
              const SizedBox(height: 12),
              TextField(
                controller: _code,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: '초대 코드',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: _loading ? null : _redeem,
                child: const Text('코드 제출'),
              ),
              // WHY: admin chrome only when server says is_admin.
              // EDGE: missing/false → hide (fail-closed). Mint still 403 server-side.
              if (access?.isAdmin == true) ...[
                const SizedBox(height: 24),
                Text('관리자', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                FilledButton.tonal(
                  onPressed: _loading ? null : _mint,
                  child: const Text('OTP 초대 코드 발급'),
                ),
                if (_minted != null) ...[
                  const SizedBox(height: 8),
                  SelectableText('방금 발급: $_minted'),
                ],
                const SizedBox(height: 12),
                Text('승인 대기 (${_pending.length})'),
                ..._pending.map((p) {
                  final uid = '${p['uid'] ?? ''}';
                  final email = '${p['email'] ?? ''}';
                  return ListTile(
                    dense: true,
                    title: Text(email.isEmpty ? uid : email),
                    subtitle: Text(uid),
                    trailing: Wrap(
                      spacing: 4,
                      children: [
                        TextButton(
                          // EDGE: do not gate on _loading (refresh) — only _mutating.
                          onPressed: _mutating
                              ? null
                              : () => _decide(uid, 'allow'),
                          child: const Text('Allow'),
                        ),
                        TextButton(
                          onPressed: _mutating
                              ? null
                              : () => _decide(uid, 'deny'),
                          child: const Text('Deny'),
                        ),
                      ],
                    ),
                  );
                }),
                if (_events.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text('알림', style: Theme.of(context).textTheme.titleSmall),
                  ..._events.take(8).map((e) {
                    return ListTile(
                      dense: true,
                      title: Text('${e['type'] ?? ''}'),
                      subtitle:
                          Text('${e['email'] ?? ''} ${e['message'] ?? ''}'),
                    );
                  }),
                ],
              ],
              // WHY: after admin Allow, invitee status stays pending until re-fetch.
              TextButton(
                onPressed: _loading ? null : _reload,
                child: const Text('새로고침'),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
          ],
        );
      },
    );
  }
}
