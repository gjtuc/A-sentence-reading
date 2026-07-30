/// App-wide auth session for the Flutter shell (email MVP · design/61).
library;

import 'package:flutter/foundation.dart';

import '../api/auth_models.dart';
import '../api/client.dart';

/// Holds current [AsrUser] and drives login/register/logout/restore.
class AuthController extends ChangeNotifier {
  AuthController({AsrClient? client}) : _client = client ?? AsrClient();

  final AsrClient _client;

  AsrClient get client => _client;

  AsrUser? user;
  AsrAuthStatus? lastStatus;
  bool bootstrapping = true;
  bool busy = false;
  String? error;

  bool get isLoggedIn => user != null && !user!.isEmpty;

  /// On cold start: load cookie → GET /api/auth/status.
  Future<void> bootstrap() async {
    bootstrapping = true;
    error = null;
    notifyListeners();
    try {
      final st = await _client.fetchAuthStatus();
      lastStatus = st;
      user = st.user;
    } catch (e) {
      // EDGE: offline / 5xx — stay logged out; keep local cookie for retry.
      error = e.toString();
      user = null;
    } finally {
      bootstrapping = false;
      notifyListeners();
    }
  }

  Future<void> loginEmail(String email, String password) async {
    await _runAuth(() => _client.loginEmail(email: email, password: password));
  }

  Future<void> registerEmail(String email, String password, {String name = ''}) async {
    await _runAuth(
      () => _client.registerEmail(email: email, password: password, name: name),
    );
  }

  Future<void> logout() async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      await _client.logout();
    } catch (e) {
      // EDGE: network fail still clears local session in client.finally
      error = e.toString();
    } finally {
      user = null;
      busy = false;
      notifyListeners();
    }
  }

  Future<void> _runAuth(Future<AsrUser> Function() op) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      // EDGE: blank email/password rejected client-side before HTTP
      final u = await op();
      user = u;
      try {
        lastStatus = await _client.fetchAuthStatus();
        if (lastStatus?.user != null) user = lastStatus!.user;
      } catch (_) {
        // keep login user if status refresh fails
      }
    } on AsrApiException catch (e) {
      error = e.message;
      rethrow;
    } catch (e) {
      error = e.toString();
      rethrow;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }
}
