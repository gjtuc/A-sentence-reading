import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/oauth_models.dart';
import '../state/auth_controller.dart';

/// Email + Google + Kakao against Cloud Run (design/61 · design/65).
///
/// OAuth is real server verification — not a UI mock. Live Enable/IPS: ASR out.

/// Client-only signup password checks (design/61 UX). Never log [password]/confirm].
///
/// Returns Korean error message or null when OK.
String? validateRegisterPasswords(String password, String confirm) {
  if (password.length < 8) {
    return '비밀번호는 8자 이상이어야 합니다.';
  }
  if (password != confirm) {
    return '비밀번호 확인이 일치하지 않습니다.';
  }
  return null;
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.auth});

  final AuthController auth;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _passwordConfirm = TextEditingController();
  final _name = TextEditingController();
  bool _registerMode = false;
  // WHY: default hidden — reduce shoulder-surfing; user opts in via eye icon.
  bool _obscurePassword = true;
  bool _obscurePasswordConfirm = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _passwordConfirm.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim();
    final password = _password.text;
    if (email.isEmpty || password.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('이메일과 비밀번호를 입력하세요.')),
      );
      return;
    }
    if (_registerMode) {
      // EDGE: mistyped password on signup — block before network (no secret logged).
      final err = validateRegisterPasswords(
        password,
        _passwordConfirm.text,
      );
      if (err != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
        return;
      }
    }
    try {
      if (_registerMode) {
        await widget.auth.registerEmail(email, password, name: _name.text);
      } else {
        await widget.auth.loginEmail(email, password);
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_registerMode ? '가입·로그인되었습니다.' : '로그인되었습니다.'),
          ),
        );
      }
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
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('카카오 로그인되었습니다.')),
        );
      }
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

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.auth,
      builder: (context, _) {
        final auth = widget.auth;
        if (auth.bootstrapping) {
          return const Center(child: CircularProgressIndicator());
        }
        if (auth.isLoggedIn) {
          final u = auth.user!;
          return Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('로그인됨', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(u.displayLabel),
                if (u.uid.isNotEmpty)
                  Text('uid: ${u.uid}', style: Theme.of(context).textTheme.bodySmall),
                if (u.providers.isNotEmpty)
                  Text(
                    'providers: ${u.providers.join(", ")}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: auth.busy ? null : () => auth.logout(),
                  child: auth.busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('로그아웃'),
                ),
                const SizedBox(height: 24),
                Text(
                  '세션은 Cloud Run asr_session (이메일 PBKDF2 · Google/카카오 실 OAuth).\n'
                  'Live Enable / IPS: Trading Gate (ASR out).',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          );
        }

        final st = auth.lastStatus;
        final emailOn = st?.emailEnabled ?? true;
        final googleOn = st?.googleEnabled ?? false;
        final kakaoOn = st?.kakaoEnabled ?? false;

        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Text('로그인', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              'Cloud Run 실계정 (이메일 · Google · 카카오). 앱에 API 비밀키 없음.',
              style: Theme.of(context).textTheme.bodySmall,
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
                _registerMode ? '이메일 가입' : '이메일 로그인',
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
              TextField(
                controller: _password,
                obscureText: _obscurePassword,
                decoration: InputDecoration(
                  labelText: '비밀번호',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    tooltip: _obscurePassword ? '비밀번호 보기' : '비밀번호 숨기기',
                    onPressed: () =>
                        setState(() => _obscurePassword = !_obscurePassword),
                    icon: Icon(
                      _obscurePassword ? Icons.visibility : Icons.visibility_off,
                    ),
                  ),
                ),
              ),
              if (_registerMode) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _passwordConfirm,
                  obscureText: _obscurePasswordConfirm,
                  decoration: InputDecoration(
                    labelText: '비밀번호 확인',
                    border: const OutlineInputBorder(),
                    suffixIcon: IconButton(
                      tooltip: _obscurePasswordConfirm
                          ? '비밀번호 보기'
                          : '비밀번호 숨기기',
                      onPressed: () => setState(
                        () => _obscurePasswordConfirm = !_obscurePasswordConfirm,
                      ),
                      icon: Icon(
                        _obscurePasswordConfirm
                            ? Icons.visibility
                            : Icons.visibility_off,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _name,
                  decoration: const InputDecoration(
                    labelText: '이름 (선택)',
                    border: OutlineInputBorder(),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton(
                onPressed: auth.busy ? null : _submit,
                child: auth.busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(_registerMode ? '가입' : '로그인'),
              ),
              TextButton(
                onPressed: auth.busy
                    ? null
                    : () => setState(() {
                      _registerMode = !_registerMode;
                      // EDGE: leaving signup — drop confirm so it cannot leak into login submit.
                      if (!_registerMode) {
                        _passwordConfirm.clear();
                        _obscurePasswordConfirm = true;
                      }
                    }),
                child: Text(_registerMode ? '이미 계정이 있나요? 로그인' : '계정이 없나요? 가입'),
              ),
            ] else
              const Text('이메일 로그인이 서버에서 꺼져 있습니다.'),
            if (auth.error != null) ...[
              const SizedBox(height: 8),
              Text(
                auth.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 24),
            Text(
              'Live Enable / IPS: Trading Gate · ASR 밖.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        );
      },
    );
  }
}
