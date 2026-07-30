/// Thin HTTP client for the existing Cloud Run FastAPI surface.
///
/// Auth (email·Google·Kakao) · library · reader · TTS (0.2.75 · design/61-65).
///
/// WHY separate from UI: screens must not know cookie jars / timeouts;
/// cookie persistence stays in this layer (design/33).
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'auth_models.dart';
import 'paper_models.dart';
import 'reading_models.dart';
import 'session_store.dart';
import 'tts_models.dart';
import 'oauth_models.dart';
import 'access_models.dart';

/// Parsed `/api/status` JSON (subset used by the mobile shell).
class AsrStatus {
  AsrStatus({
    required this.ok,
    required this.version,
    required this.pipeline,
    this.mobileFlutterScaffold = false,
    this.mobileAndroidPlatform = false,
    this.mobileEmailAuth = false,
    this.mobileLibrary = false,
    this.mobileReader = false,
    this.mobileTts = false,
    this.mobileOauth = false,
    this.mobileTheme = false,
    this.mobileAccessGate = false,
  });

  /// Tolerant parse: missing keys become empty strings / false — never throw on
  /// partial JSON (edge: older Cloud Run without newer flags).
  factory AsrStatus.fromJson(Map<String, dynamic> json) {
    return AsrStatus(
      ok: json['ok'] == true,
      version: '${json['version'] ?? ''}',
      pipeline: '${json['pipeline'] ?? json['pipeline_version'] ?? ''}',
      mobileFlutterScaffold: json['mobile_flutter_scaffold'] == true,
      mobileAndroidPlatform: json['mobile_android_platform'] == true,
      mobileEmailAuth: json['mobile_email_auth'] == true,
      mobileLibrary: json['mobile_library'] == true,
      mobileReader: json['mobile_reader'] == true,
      mobileTts: json['mobile_tts'] == true,
      mobileOauth: json['mobile_oauth'] == true,
      mobileTheme: json['mobile_theme'] == true,
      mobileAccessGate: json['mobile_access_gate'] == true || json['access_gate'] == true,
    );
  }

  final bool ok;
  final String version;
  final String pipeline;
  final bool mobileFlutterScaffold;
  final bool mobileAndroidPlatform;
  final bool mobileEmailAuth;
  final bool mobileLibrary;
  final bool mobileReader;
  final bool mobileTts;
  final bool mobileOauth;
  final bool mobileTheme;
  final bool mobileAccessGate;
}

class AsrClient {
  AsrClient({
    AsrConfig? config,
    http.Client? httpClient,
    SessionStore? sessionStore,
  })  : _config = config ?? AsrConfig(),
        _http = httpClient ?? http.Client(),
        _sessions = sessionStore ?? PrefsSessionStore();

  final AsrConfig _config;
  final http.Client _http;
  final SessionStore _sessions;

  /// Test / UI access to the same store the client mutates.
  SessionStore get sessionStore => _sessions;

  Uri _uri(String path) {
    final p = path.startsWith('/') ? path : '/$path';
    return Uri.parse('${_config.effectiveBaseUrl}$p');
  }

  Future<Map<String, String>> _headers({bool jsonBody = false}) async {
    final h = <String, String>{};
    if (jsonBody) {
      h['Content-Type'] = 'application/json; charset=utf-8';
      h['Accept'] = 'application/json';
    }
    final token = await _sessions.readToken();
    if (token != null && token.isNotEmpty) {
      h['Cookie'] = '$kAsrSessionCookieName=$token';
    }
    return h;
  }

  Future<void> _captureSession(http.Response res) async {
    // package:http exposes a single set-cookie string (may join multiples).
    final setCookie = res.headers['set-cookie'];
    final parsed = parseAsrSessionCookie(setCookie);
    if (parsed != null) {
      await _sessions.writeToken(parsed);
    }
  }

  Map<String, dynamic> _decodeObject(http.Response res, String label) {
    if (res.statusCode < 200 || res.statusCode >= 300) {
      String detail = '$label HTTP ${res.statusCode}';
      try {
        final body = jsonDecode(res.body);
        if (body is Map && body['message'] != null) {
          detail = '${body['message']}';
        } else if (body is Map && body['error'] != null) {
          detail = '${body['error']}';
        }
      } catch (_) {
        // EDGE: HTML / empty error pages
      }
      throw AsrApiException(detail, res.statusCode);
    }
    final body = jsonDecode(res.body);
    if (body is! Map<String, dynamic>) {
      if (body is Map) {
        return Map<String, dynamic>.from(body);
      }
      throw AsrApiException('$label body is not a JSON object', res.statusCode);
    }
    return body;
  }

  /// GET /api/status — health / version probe for the home shell.
  Future<AsrStatus> fetchStatus() async {
    final res = await _http
        .get(_uri('/api/status'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    final map = _decodeObject(res, 'status');
    return AsrStatus.fromJson(map);
  }

  /// GET /api/auth/status — session restore / provider flags.
  Future<AsrAuthStatus> fetchAuthStatus() async {
    final res = await _http
        .get(_uri('/api/auth/status'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    await _captureSession(res);
    final map = _decodeObject(res, 'auth/status');
    return AsrAuthStatus.fromJson(map);
  }


  /// POST /api/auth/google — real id_token verification on server (design/23·65).
  Future<AsrUser> loginGoogle({required String credential, String mode = 'login'}) async {
    if (!isUsableGoogleCredential(credential)) {
      throw AsrApiException('invalid_token', 401);
    }
    final res = await _http
        .post(
          _uri('/api/auth/google'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'credential': credential.trim(),
            'mode': mode.trim().isEmpty ? 'login' : mode.trim(),
          }),
        )
        .timeout(const Duration(seconds: 30));
    await _captureSession(res);
    final map = _decodeObject(res, 'auth/google');
    final userRaw = map['user'];
    final user = AsrUser.fromJson(
      userRaw is Map ? Map<String, dynamic>.from(userRaw) : null,
    );
    if (user.isEmpty) {
      throw AsrApiException('google login returned empty user', res.statusCode);
    }
    return user;
  }

  /// Persist a session token from Kakao mobile deep link (no Set-Cookie path).
  Future<AsrUser> applySessionToken(String token) async {
    final t = token.trim();
    if (t.isEmpty || t.toLowerCase() == 'deleted') {
      throw AsrApiException('missing_session', 401);
    }
    await _sessions.writeToken(t);
    final st = await fetchAuthStatus();
    final u = st.user;
    if (u == null || u.isEmpty) {
      await _sessions.clear();
      throw AsrApiException('session not accepted', 401);
    }
    return u;
  }

  /// Absolute URL for Kakao Custom-Tab start (mobile=1).
  String kakaoStartUrl({String mode = 'login'}) {
    final m = mode.trim().isEmpty ? 'login' : mode.trim();
    return _uri('/api/auth/kakao/start').replace(
      queryParameters: {'mode': m, 'mobile': '1'},
    ).toString();
  }

  /// POST /api/auth/email/login — sets `asr_session` cookie on success.
  Future<AsrUser> loginEmail({
    required String email,
    required String password,
  }) async {
    final res = await _http
        .post(
          _uri('/api/auth/email/login'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'email': email.trim(),
            'password': password,
          }),
        )
        .timeout(const Duration(seconds: 30));
    await _captureSession(res);
    final map = _decodeObject(res, 'email/login');
    final userRaw = map['user'];
    final user = AsrUser.fromJson(
      userRaw is Map ? Map<String, dynamic>.from(userRaw) : null,
    );
    if (user.isEmpty) {
      throw AsrApiException('email/login returned empty user', res.statusCode);
    }
    return user;
  }

  /// POST /api/auth/email/register — same cookie capture as login.
  Future<AsrUser> registerEmail({
    required String email,
    required String password,
    String name = '',
  }) async {
    final res = await _http
        .post(
          _uri('/api/auth/email/register'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'email': email.trim(),
            'password': password,
            'name': name.trim(),
          }),
        )
        .timeout(const Duration(seconds: 30));
    await _captureSession(res);
    final map = _decodeObject(res, 'email/register');
    final userRaw = map['user'];
    final user = AsrUser.fromJson(
      userRaw is Map ? Map<String, dynamic>.from(userRaw) : null,
    );
    if (user.isEmpty) {
      throw AsrApiException('email/register returned empty user', res.statusCode);
    }
    return user;
  }


  /// GET /api/cache/papers — authenticated library listing.
  ///
  /// EDGE: non-list `papers` · null entries · missing id/title → skipped.
  Future<List<PaperEntry>> listPapers() async {
    final res = await _http
        .get(_uri('/api/cache/papers'), headers: await _headers())
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'cache/papers');
    final raw = map['papers'];
    if (raw is! List) {
      // EDGE: ok:true but papers missing/wrong type → empty library
      return const [];
    }
    final out = <PaperEntry>[];
    for (final item in raw) {
      if (item is! Map) continue;
      final e = PaperEntry.fromJson(Map<String, dynamic>.from(item));
      if (e.isValid) out.add(e);
    }
    return out;
  }

  /// POST /api/cache/papers/{id}/open — start a reading session from cache.
  Future<ReadingSession> openPaper(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/open'),
          headers: await _headers(jsonBody: true),
          body: '{}',
        )
        .timeout(const Duration(seconds: 120));
    final map = _decodeObject(res, 'cache/open');
    final opened = ReadingSession.fromOpenJson(map);
    if (!opened.isValid) {
      throw AsrApiException('open returned empty session_id', res.statusCode);
    }
    return opened;
  }

  /// PATCH /api/session/{id}/cursor — best-effort sync (local UI stays source of truth on fail).
  Future<void> patchCursor({
    required String sessionId,
    int? sentenceIndex,
    int? figureIndex,
  }) async {
    final sid = sessionId.trim();
    if (sid.isEmpty) {
      throw AsrApiException('session id is empty', 400);
    }
    final body = <String, dynamic>{};
    if (sentenceIndex != null) body['sentence_index'] = sentenceIndex;
    if (figureIndex != null) body['figure_index'] = figureIndex;
    // EDGE: nothing to patch
    if (body.isEmpty) return;
    final res = await _http
        .patch(
          _uri('/api/session/${Uri.encodeComponent(sid)}/cursor'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 20));
    _decodeObject(res, 'session/cursor');
  }


  /// GET /api/tts/voices — availability + curated list (edge: missing fields → defaults).
  Future<TtsVoicesInfo> fetchTtsVoices() async {
    final res = await _http
        .get(_uri('/api/tts/voices'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    final map = _decodeObject(res, 'tts/voices');
    return TtsVoicesInfo.fromJson(map);
  }

  /// POST /api/tts — returns raw MP3 bytes (do not JSON-decode success body).
  ///
  /// EDGE: empty text refused locally; 4xx/5xx JSON errors decoded for message.
  Future<Uint8List> synthesizeTts({
    required String text,
    String? voice,
    double speakingRate = kTtsRateDefault,
  }) async {
    if (isEmptyTtsText(text)) {
      throw AsrApiException('empty_text', 400);
    }
    final rate = clampSpeakingRate(speakingRate);
    final payload = <String, dynamic>{
      'text': text.trim(),
      'speaking_rate': rate,
    };
    final v = (voice ?? '').trim();
    if (v.isNotEmpty) payload['voice'] = v;

    final headers = await _headers(jsonBody: true);
    headers['Accept'] = 'audio/mpeg, application/json';

    final res = await _http
        .post(
          _uri('/api/tts'),
          headers: headers,
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 60));

    final ctHdr = (res.headers['content-type'] ?? '').toLowerCase();
    final okAudio = res.statusCode >= 200 &&
        res.statusCode < 300 &&
        (ctHdr.contains('audio') ||
            (res.bodyBytes.isNotEmpty && !ctHdr.contains('json')));
    if (okAudio) {
      if (res.bodyBytes.isEmpty) {
        throw AsrApiException('empty audio body', res.statusCode);
      }
      return res.bodyBytes;
    }

    String detail = 'tts HTTP ${res.statusCode}';
    try {
      final body = jsonDecode(res.body);
      if (body is Map) {
        if (body['message'] != null) {
          detail = '${body['message']}';
        } else if (body['error'] != null) {
          detail = '${body['error']}';
        }
      }
    } catch (_) {
      // EDGE: non-JSON error page
    }
    throw AsrApiException(detail, res.statusCode);
  }


  /// GET /api/access/status
  Future<AccessStatus> fetchAccessStatus() async {
    final res = await _http
        .get(_uri('/api/access/status'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    final map = _decodeObject(res, 'access/status');
    return AccessStatus.fromJson(map);
  }

  /// POST /api/access/invite — redeem OTP-style code → pending.
  Future<AccessStatus> redeemInviteCode(String code) async {
    final compact = normalizeInviteCodeInput(code);
    if (compact.isEmpty) {
      throw AsrApiException('empty_code', 400);
    }
    if (compact.length != 8) {
      throw AsrApiException('bad_code', 403);
    }
    final res = await _http
        .post(
          _uri('/api/access/invite'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'code': compact}),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'access/invite');
    final access = map['access'];
    if (access is Map) {
      return AccessStatus.fromJson(Map<String, dynamic>.from(access));
    }
    return AccessStatus.fromJson(map);
  }

  /// POST /api/access/admin/mint — returns plaintext once.
  Future<String> mintInviteCode({String note = ''}) async {
    final res = await _http
        .post(
          _uri('/api/access/admin/mint'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'note': note}),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'access/mint');
    final code = '${map['code'] ?? ''}'.trim();
    if (code.isEmpty) {
      throw AsrApiException('mint returned empty code', res.statusCode);
    }
    return code;
  }

  /// GET /api/access/admin/pending
  Future<List<Map<String, dynamic>>> fetchAccessPending() async {
    final res = await _http
        .get(_uri('/api/access/admin/pending'), headers: await _headers())
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'access/pending');
    final raw = map['pending'];
    if (raw is! List) return const [];
    return [
      for (final item in raw)
        if (item is Map) Map<String, dynamic>.from(item),
    ];
  }

  /// GET /api/access/admin/notifications
  Future<List<Map<String, dynamic>>> fetchAccessNotifications() async {
    final res = await _http
        .get(
          _uri('/api/access/admin/notifications'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'access/notifications');
    final raw = map['events'];
    if (raw is! List) return const [];
    return [
      for (final item in raw)
        if (item is Map) Map<String, dynamic>.from(item),
    ];
  }

  /// POST /api/access/admin/decide
  Future<AccessStatus> decideAccess({
    required String uid,
    required String decision,
    String note = '',
  }) async {
    final res = await _http
        .post(
          _uri('/api/access/admin/decide'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'uid': uid.trim(),
            'decision': decision.trim(),
            'note': note,
          }),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'access/decide');
    final access = map['access'];
    if (access is Map) {
      return AccessStatus.fromJson(Map<String, dynamic>.from(access));
    }
    return AccessStatus.fromJson(map);
  }

  /// POST /api/auth/logout — clears server cookie + local token.
  Future<void> logout() async {
    try {
      final res = await _http
          .post(
            _uri('/api/auth/logout'),
            headers: await _headers(jsonBody: true),
            body: '{}',
          )
          .timeout(const Duration(seconds: 20));
      // Best-effort: even non-2xx we clear local token (edge: already expired).
      if (res.statusCode >= 200 && res.statusCode < 300) {
        await _captureSession(res);
      }
    } finally {
      await _sessions.clear();
    }
  }

  void close() => _http.close();
}

class AsrApiException implements Exception {
  AsrApiException(this.message, [this.statusCode]);

  final String message;
  final int? statusCode;

  @override
  String toString() => 'AsrApiException($message, status=$statusCode)';
}
