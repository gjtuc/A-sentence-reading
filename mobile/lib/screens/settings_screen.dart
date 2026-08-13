import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/access_models.dart';
import '../api/client.dart';
import '../api/theme_models.dart';
import '../api/tts_models.dart';
import '../state/auth_controller.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/theme_controller.dart';
import '../state/translate_controller.dart';
import '../state/tts_controller.dart';
import 'error_logs_screen.dart';

/// Settings: account, theme, TTS, translate, shadowing, access (design/66-68, 79, 96, 99, 103, 104).
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.theme,
    required this.auth,
    required this.shadowing,
    required this.tts,
    required this.translate,
    required this.library,
  });

  final ThemeController theme;
  final AuthController auth;
  final ShadowingController shadowing;
  final TtsController tts;
  final TranslateController translate;
  final LibraryController library;

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
  /// design/130 — admin unread cloud error count (settings badge).
  int _errorBadge = 0;

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
        _errorBadge = 0;
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
      var badge = 0;
      // Admin endpoints 403 for non-admins — ignore.
      try {
        pending = await widget.auth.client.fetchAccessPending();
        events = await widget.auth.client.fetchAccessNotifications();
      } catch (_) {}
      if (st.isAdmin) {
        try {
          badge = await widget.auth.client.fetchAdminErrorBadge();
        } catch (_) {
          badge = 0;
        }
      }
      if (!mounted) return;
      setState(() {
        _access = st;
        _pending = pending;
        _events = events.reversed.take(20).toList();
        _errorBadge = badge;
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
      animation: Listenable.merge([
        widget.theme,
        widget.auth,
        widget.shadowing,
        widget.translate,
        widget.library,
      ]),
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
            // WHY: admin-only — cloud error triage replaces status dump (design/130).
            // EDGE: non-admin must not see others' logs (server still 403).
            if (access?.isAdmin == true) ...[
              const SizedBox(height: 8),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Badge(
                  isLabelVisible: _errorBadge > 0,
                  label: Text(_errorBadge > 99 ? '99+' : '$_errorBadge'),
                  child: const Icon(Icons.bug_report_outlined),
                ),
                title: const Text('오류 로그'),
                subtitle: const Text('클라우드에 모인 오류 보기'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async {
                  await Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => ErrorLogsScreen(
                        client: widget.auth.client,
                      ),
                    ),
                  );
                  if (mounted) _reload();
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
            Text('TTS', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              '읽기와 연습(쉐도잉) 듣기에 공통입니다. 서버는 1.0으로 합성하고 배속은 기기에서만 적용합니다.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            AnimatedBuilder(
              animation: widget.tts,
              builder: (context, _) {
                final tts = widget.tts;
                final random = tts.isRandomMode;
                final voiceItems = tts.voices.isEmpty
                    ? <DropdownMenuItem<String>>[
                        DropdownMenuItem(
                          value: tts.voice,
                          child: Text(tts.voice, overflow: TextOverflow.ellipsis),
                        ),
                      ]
                    : tts.voices
                        .map(
                          (v) => DropdownMenuItem(
                            value: v.id,
                            child: Text(v.label, overflow: TextOverflow.ellipsis),
                          ),
                        )
                        .toList(growable: false);
                final voiceValue = voiceItems.any((e) => e.value == tts.voice)
                    ? tts.voice
                    : (voiceItems.first.value ?? kTtsDefaultVoice);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    DropdownButtonFormField<String>(
                      key: const ValueKey('tts_mode'),
                      decoration: const InputDecoration(
                        labelText: '모드',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      value: normalizeTtsMode(tts.mode),
                      items: [
                        for (final m in [
                          kTtsModeFixed,
                          kTtsModeRandomNormal,
                          kTtsModeRandomHard,
                          kTtsModeRandomVeryHard,
                        ])
                          DropdownMenuItem(
                            value: m,
                            child: Text(ttsModeLabelKo(m)),
                          ),
                      ],
                      onChanged: (v) {
                        if (v == null) return;
                        tts.setMode(v);
                      },
                    ),
                    const SizedBox(height: 6),
                    Text(
                      ttsModeHintKo(tts.mode),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 12),
                    Opacity(
                      opacity: random ? 0.45 : 1,
                      child: IgnorePointer(
                        ignoring: random,
                        child: DropdownButtonFormField<String>(
                          key: const ValueKey('tts_voice'),
                          decoration: InputDecoration(
                            labelText: '목소리',
                            border: const OutlineInputBorder(),
                            isDense: true,
                            helperText: tts.voicesLoading
                                ? '목소리 목록 불러오는 중…'
                                : null,
                          ),
                          value: voiceValue,
                          items: voiceItems,
                          onChanged: (v) {
                            if (v == null) return;
                            tts.setVoice(v);
                          },
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Opacity(
                      opacity: random ? 0.45 : 1,
                      child: IgnorePointer(
                        ignoring: random,
                        child: Row(
                          children: [
                            const Text('배속', style: TextStyle(fontSize: 14)),
                            Expanded(
                              child: Slider(
                                value: tts.rate.clamp(kTtsRateMin, kTtsRateMax),
                                min: kTtsRateMin,
                                max: kTtsRateMax,
                                divisions: 17,
                                label: tts.rate.toStringAsFixed(2),
                                onChanged: (v) => tts.setRate(v),
                              ),
                            ),
                            SizedBox(
                              width: 44,
                              child: Text(
                                tts.rate.toStringAsFixed(2),
                                textAlign: TextAlign.end,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (tts.voices.isEmpty && !tts.voicesLoading)
                      TextButton(
                        onPressed: () => tts.ensureVoicesLoaded(force: true),
                        child: const Text('목소리 목록 다시 불러오기'),
                      ),
                  ],
                );
              },
            ),
            const Divider(height: 32),
            Text('번역', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              '기본은 꺼져 있습니다. 끄면 문서 만들 때 번역하지 않고, 켠 뒤 그 문서를 열면 번역을 채웁니다.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('번역 사용'),
              value: widget.translate.enabled,
              onChanged: !logged
                  ? null
                  : (v) async {
                      await widget.translate.setEnabled(v);
                      // design/99 — turning ON while a paper is open → re-open for KO backfill.
                      if (!v) return;
                      final cacheId =
                          (widget.library.session?.cacheId ?? '').trim();
                      if (cacheId.isEmpty) return;
                      await widget.library.openByCacheId(cacheId);
                    },
            ),
            if (widget.translate.error != null)
              Text(
                widget.translate.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            const Divider(height: 32),
            Text('쉐도잉 연습', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              widget.shadowing.serverAvailable
                  ? '기본은 꺼져 있습니다. 켜면 문장 따라 말하기 연습을 씁니다 (연습 화면은 후속 연결).'
                  : '서버에서 이 기능이 꺼져 있습니다. 켠 것처럼 보이지 않습니다.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('쉐도잉 연습 사용'),
              value: widget.shadowing.serverAvailable && widget.shadowing.enabled,
              // WHY: kill off → null onChanged (disabled); no false success.
              onChanged: (!logged || !widget.shadowing.serverAvailable)
                  ? null
                  : (v) => widget.shadowing.setEnabled(v),
            ),
            if (widget.shadowing.error != null)
              Text(
                widget.shadowing.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            // design/104 — invite redeem only for none/pending/denied non-admin.
            // Admin keeps mint/Allow/Deny but does not self-redeem.
            if (logged) ...[
              const SizedBox(height: 8),
              if (_loading) const LinearProgressIndicator(),
              if (shouldShowSettingsInviteRedeem(access)) ...[
                const Divider(height: 32),
                Text(
                  '액세스 (초대 코드)',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  access?.isDenied == true
                      ? '거절되었습니다. 새 초대 코드를 다시 입력할 수 있습니다.'
                      : '관리자에게 부여받은 OTP를 입력하면 승인 대기가 됩니다.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
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
              ],
              // WHY: admin chrome only when server says is_admin.
              // EDGE: missing/false → hide (fail-closed). Mint still 403 server-side.
              if (access?.isAdmin == true) ...[
                const Divider(height: 32),
                Text('관리자', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(
                  '초대 코드 발급과 승인만 합니다. 본인 초대 입력은 필요 없습니다.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
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
              if (shouldShowSettingsInviteRedeem(access) ||
                  access?.isAdmin == true)
                TextButton(
                  onPressed: _loading ? null : _reload,
                  child: const Text('새로고침'),
                ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            // design/134 — localhost-only hang E2E (never on Cloud Run host).
            if (widget.auth.client.isLocalDevHost) ...[
              const Divider(height: 32),
              Semantics(
                button: true,
                label: '업로드 hang 시뮬 (로컬)',
                child: ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('업로드 hang 시뮬 (로컬)'),
                  subtitle: Text(
                    widget.library.error ??
                        '진전 없이 stall 초가 지나면 실패 문구가 뜹니다.',
                  ),
                  onTap: () async {
                    final ok =
                        await widget.library.simulateIngestHangForLocalE2E();
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          ok
                              ? 'hang 감시 시작 — stall 후 실패 UI를 확인하세요.'
                              : '로컬 API에서만 사용할 수 있습니다.',
                        ),
                      ),
                    );
                  },
                ),
              ),
              if (widget.library.error != null)
                Text(
                  widget.library.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
            ],
          ],
        );
      },
    );
  }
}
