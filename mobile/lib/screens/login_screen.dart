import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/oauth_models.dart';
import '../state/auth_controller.dart';

/// Google · Kakao · email magic-link login (design/65 · 77 · 78).
///
/// WHY (design/78): no email+password signup/login fields — do not collect
/// passwords into cloud accounts. Magic-link covers email sign-in.

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.auth});

  final AuthController auth;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _google() async {
    try {
      await widget.auth.loginGoogle();
      if (!mounted) return;
      // WHY: never show success unless session user is present (fail-closed).
      if (widget.auth.user == null) {
        final msg = widget.auth.error ?? 'Google 로그인에 실패했습니다.';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Google 로그인되었습니다.')),
      );
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (e) {
      if (mounted) {
        final msg = widget.auth.error ?? describeGoogleSignInFailure(e);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    }
  }

  Future<void> _kakao() async {
    try {
      await widget.auth.loginKakao();
      if (!mounted) return;
      // WHY: never show success unless session user is present (fail-closed).
      if (widget.auth.user == null) {
        final msg = widget.auth.error ?? '카카오 로그인에 실패했습니다.';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('카카오 로그인되었습니다.')),
      );
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _magicLink() async {
    final email = _email.text.trim();
    if (email.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('이메일을 입력한 뒤 로그인 링크를 요청하세요.')),
      );
      return;
    }
    try {
      await widget.auth.requestMagicLink(email);
      if (!mounted) return;
      final hint = widget.auth.magicLinkHint ?? '로그인 링크를 이메일로 보냈습니다.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (e) {
      if (mounted) {
        final msg = widget.auth.error ?? '$e';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.auth,
      builder: (context, _) {
        final auth = widget.auth;
        if (auth.bootstrapping) {
          return const Center(child: CircularProgressIndicator());
        }
        // WHY: account chrome lives in Settings (design/68). HomeShell hides this
        // screen when logged in; if we still get here mid-transition, stay quiet.
        if (auth.isLoggedIn) {
          return const Center(child: CircularProgressIndicator());
        }

        final st = auth.lastStatus;
        final emailOn = st?.emailEnabled ?? true;
        final googleOn = st?.googleEnabled ?? false;
        final kakaoOn = st?.kakaoEnabled ?? false;

        return LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: constraints.maxHeight - 48,
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      '로그인',
                      style: Theme.of(context).textTheme.titleLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                    if (googleOn)
                      FilledButton.tonal(
                        onPressed: auth.busy ? null : _google,
                        child: const Text('Google로 계속'),
                      ),
                    if (kakaoOn) ...[
                      const SizedBox(height: 8),
                      FilledButton.tonal(
                        onPressed: auth.busy ? null : _kakao,
                        child: const Text('카카오로 계속'),
                      ),
                    ],
                    if (googleOn || kakaoOn) const Divider(height: 32),
                    if (emailOn) ...[
                      Text(
                        '이메일 로그인 링크',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        autocorrect: false,
                        decoration: const InputDecoration(
                          labelText: '이메일',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 12),
                      FilledButton(
                        onPressed: auth.busy ? null : _magicLink,
                        child: auth.busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('이메일로 로그인 링크 받기'),
                      ),
                    ] else
                      const Text('이메일 로그인이 서버에서 꺼져 있습니다.'),
                    if (auth.error != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        auth.error!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}
