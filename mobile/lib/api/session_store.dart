/// Persists the Cloud Run `asr_session` cookie value on-device.
///
/// WHY not full CookieJar yet: MVP only needs one httponly session name
/// (design/33 · design/61). SharedPreferences holds the opaque token;
/// secrets (Gemini/GCS) never land here.
library;

import 'package:shared_preferences/shared_preferences.dart';

const String kAsrSessionCookieName = 'asr_session';
const String _prefsKey = 'asr.session.v1';

/// Abstract store so unit tests can inject memory without Flutter plugins.
abstract class SessionStore {
  Future<String?> readToken();

  Future<void> writeToken(String? token);

  Future<void> clear();
}

/// SharedPreferences-backed store (production / integration).
class PrefsSessionStore implements SessionStore {
  PrefsSessionStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<String?> readToken() async {
    final p = await _ready();
    final v = p.getString(_prefsKey);
    if (v == null) return null;
    final t = v.trim();
    // EDGE: empty / whitespace-only → treat as logged out
    return t.isEmpty ? null : t;
  }

  @override
  Future<void> writeToken(String? token) async {
    final p = await _ready();
    if (token == null || token.trim().isEmpty) {
      await p.remove(_prefsKey);
      return;
    }
    await p.setString(_prefsKey, token.trim());
  }

  @override
  Future<void> clear() => writeToken(null);
}

/// In-memory store for widget/unit tests (no plugin channel).
class MemorySessionStore implements SessionStore {
  String? _token;

  @override
  Future<String?> readToken() async => _token;

  @override
  Future<void> writeToken(String? token) async {
    if (token == null || token.trim().isEmpty) {
      _token = null;
    } else {
      _token = token.trim();
    }
  }

  @override
  Future<void> clear() => writeToken(null);
}

/// Pull `asr_session` out of a raw `Set-Cookie` header (or joined headers).
///
/// EDGE cases: null/empty · wrong cookie name · deleted/empty value ·
/// extra attributes (`Path=`, `HttpOnly`, …) · multiple cookies in one string.
String? parseAsrSessionCookie(String? setCookieHeader) {
  if (setCookieHeader == null) return null;
  final raw = setCookieHeader.trim();
  if (raw.isEmpty) return null;

  final re = RegExp(
    r'(?:^|[,;\s])asr_session=([^;,\s]*)',
    caseSensitive: false,
  );
  final m = re.firstMatch(raw);
  if (m == null) {
    final bare = RegExp(
      r'^asr_session=([^;]*)',
      caseSensitive: false,
    ).firstMatch(raw);
    if (bare == null) return null;
    return _normalizeCookieValue(bare.group(1));
  }
  return _normalizeCookieValue(m.group(1));
}

String? _normalizeCookieValue(String? raw) {
  if (raw == null) return null;
  var v = raw.trim();
  if (v.startsWith('"') && v.endsWith('"') && v.length >= 2) {
    v = v.substring(1, v.length - 1).trim();
  }
  if (v.isEmpty) return null;
  final lower = v.toLowerCase();
  if (lower == 'deleted' || lower == 'null' || lower == 'undefined') {
    return null;
  }
  return v;
}
