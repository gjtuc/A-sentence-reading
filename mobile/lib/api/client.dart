/// Thin HTTP client for the existing Cloud Run FastAPI surface.
///
/// Auth (email·Google·Kakao) · library · reader · TTS (0.2.75 · design/61-65).
///
/// WHY separate from UI: screens must not know cookie jars / timeouts;
/// cookie persistence stays in this layer (design/33).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import '../services/evidence_bus.dart';
import 'auth_models.dart';
import 'paper_models.dart';
import 'reading_models.dart';
import 'session_store.dart';
import 'tts_models.dart';
import 'oauth_models.dart';
import 'access_models.dart';
import 'ingest_models.dart';

/// design/169g — snake-safe message fingerprint for progress_view (no paper text).
String _progressMsgHash(String msg) {
  final digest = sha256.convert(utf8.encode(msg));
  return 'h_${digest.toString().substring(0, 12)}';
}

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
    this.mobileUpload = false,
    this.mobileUploadBackground = false,
    this.mobileUploadInterruptResume = false,
    this.mobileUploadWorkmanager = false,
    this.mobileEmailMagicLink = true,
    // design/79 — missing key → off (fail-closed; practice not ready by default).
    this.mobileShadowingPractice = false,
    this.mobileShadowingChunks = false,
    this.mobileShadowingPracticeLoop = false,
    // design/83 — missing key → on (fail-closed; require login).
    this.mobileLoginRequired = true,
    // design/84 — missing key → on (fail-closed; waiting shell).
    this.mobileAccessWaitingUx = true,
    // design/123 — missing key → fail-closed (refuse bad progress).
    this.progressFailClosed = true,
    // design/28 · 124 — missing key → on (show Fig chips when server advertises).
    this.figRefHints = true,
    // design/130 — missing key → on (report); explicit false kills.
    this.cloudErrorLogs = true,
    this.mobileCloudErrorLogs = true,
    // design/131 — missing → full captions; explicit false restores 2-line ….
    this.captionFullText = true,
    // design/132 — missing → on; explicit false kills cancel UI.
    this.mobileIngestCancel = true,
    // design/134 — missing → on; explicit false skips upload hang watchdog.
    this.mobileIngestUploadHang = true,
    this.ingestHangStallSeconds = 180,
    // design/148 — missing key → on; explicit false kills mobile cite panel.
    this.mobileCiteRefPanel = true,
    this.mobileThisPaperPanel = true,
    this.citeRefOpen = true,
    // design/149 — missing key → on; caption in composite PNG, hide under-image Text.
    this.figureCaptionInImage = true,
    this.mobileFigureCaptionInImage = true,
    this.bookmarksSync = false,
    this.annotationsSync = false,
    this.mobileApkUrl = '',
    // design/169 — missing → off (fail-closed; no client evidence spam).
    this.evidenceBus = false,
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
      mobileUpload: json['mobile_upload'] == true,
      // design/74 — kill switch only when server sends false.
      // Missing key (pre-0.2.91): allow FG so sideload E2E works before CD.
      mobileUploadBackground: json.containsKey('mobile_upload_background')
          ? json['mobile_upload_background'] == true
          : true,
      // design/75 — missing key → on (sideload before CD); explicit false kills.
      mobileUploadInterruptResume:
          json.containsKey('mobile_upload_interrupt_resume')
              ? json['mobile_upload_interrupt_resume'] == true
              : true,
      // design/76 — missing key → on; explicit false kills WorkManager enqueue.
      mobileUploadWorkmanager: json.containsKey('mobile_upload_workmanager')
          ? json['mobile_upload_workmanager'] == true
          : true,
      // design/77 — missing key → on; explicit false hides magic-link UI.
      mobileEmailMagicLink: json.containsKey('mobile_email_magic_link')
          ? json['mobile_email_magic_link'] == true
          : true,
      // design/79 — missing / false → opt-in UI disabled (server kill).
      mobileShadowingPractice: json['mobile_shadowing_practice'] == true ||
          json['shadowing_practice'] == true,
      mobileShadowingChunks: json['mobile_shadowing_chunks'] == true ||
          json['shadowing_chunks'] == true,
      mobileShadowingPracticeLoop: json['mobile_shadowing_practice_loop'] == true ||
          json['shadowing_practice_loop'] == true,
      // design/83 — missing key → require login (fail-closed).
      mobileLoginRequired: json.containsKey('mobile_login_required')
          ? json['mobile_login_required'] == true
          : (json.containsKey('login_required')
              ? json['login_required'] == true
              : true),
      // design/84 — missing key → waiting UX on.
      mobileAccessWaitingUx: json.containsKey('mobile_access_waiting_ux')
          ? json['mobile_access_waiting_ux'] == true
          : (json.containsKey('access_waiting_ux')
              ? json['access_waiting_ux'] == true
              : true),
      // design/123 — missing key → fail-closed; explicit false enables clamp kill.
      progressFailClosed: json.containsKey('progress_fail_closed')
          ? json['progress_fail_closed'] == true
          : true,
      // design/124 — missing key → show chips; explicit false hides (server kill).
      figRefHints: json.containsKey('fig_ref_hints')
          ? json['fig_ref_hints'] == true
          : true,
      // design/130 — missing → on; explicit false kills reporting.
      cloudErrorLogs: json.containsKey('cloud_error_logs')
          ? json['cloud_error_logs'] == true
          : true,
      mobileCloudErrorLogs: json.containsKey('mobile_cloud_error_logs')
          ? json['mobile_cloud_error_logs'] == true
          : (json.containsKey('cloud_error_logs')
              ? json['cloud_error_logs'] == true
              : true),
      // design/131 — missing → full; explicit false restores ellipsis.
      captionFullText: json.containsKey('caption_full_text')
          ? json['caption_full_text'] == true
          : true,
      // design/132 — missing → on; explicit false kills cancel.
      mobileIngestCancel: json.containsKey('mobile_ingest_cancel')
          ? json['mobile_ingest_cancel'] == true
          : (json.containsKey('ingest_cancel')
              ? json['ingest_cancel'] == true
              : true),
      // design/134 — missing → on; explicit false kills upload hang.
      mobileIngestUploadHang: json.containsKey('mobile_ingest_upload_hang')
          ? json['mobile_ingest_upload_hang'] == true
          : (json.containsKey('ingest_upload_hang')
              ? json['ingest_upload_hang'] == true
              : true),
      ingestHangStallSeconds: () {
        final raw = json['ingest_hang_stall_seconds'];
        if (raw is int) return raw.clamp(5, 3600);
        if (raw is num) return raw.toInt().clamp(5, 3600);
        final p = int.tryParse('$raw');
        return (p ?? 180).clamp(5, 3600);
      }(),
      // design/148 — missing → on; explicit false kills panel.
      mobileCiteRefPanel: json.containsKey('mobile_cite_ref_panel')
          ? json['mobile_cite_ref_panel'] == true
          : true,
      mobileThisPaperPanel: json.containsKey('mobile_this_paper_panel')
          ? json['mobile_this_paper_panel'] == true
          : true,
      citeRefOpen: json.containsKey('cite_ref_open')
          ? json['cite_ref_open'] == true
          : true,
      figureCaptionInImage: json.containsKey('figure_caption_in_image')
          ? json['figure_caption_in_image'] == true
          : true,
      mobileFigureCaptionInImage: json.containsKey('mobile_figure_caption_in_image')
          ? json['mobile_figure_caption_in_image'] == true
          : (json.containsKey('figure_caption_in_image')
              ? json['figure_caption_in_image'] == true
              : true),
      bookmarksSync: () {
        final gcs = json['gcs'];
        if (gcs is Map && gcs.containsKey('bookmarks_sync')) {
          return gcs['bookmarks_sync'] == true;
        }
        return json['bookmarks_sync'] == true;
      }(),
      annotationsSync: () {
        final gcs = json['gcs'];
        if (gcs is Map && gcs.containsKey('annotations_sync')) {
          return gcs['annotations_sync'] == true;
        }
        return json['annotations_sync'] == true;
      }(),
      mobileApkUrl: '${json['mobile_apk_url'] ?? ''}'.trim(),
      // design/169 — missing → off; explicit true enables EvidenceBus flush.
      evidenceBus: json['evidence_bus'] == true,
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
  final bool mobileUpload;
  final bool mobileUploadBackground;
  final bool mobileUploadInterruptResume;
  final bool mobileUploadWorkmanager;
  final bool mobileEmailMagicLink;
  final bool mobileShadowingPractice;
  final bool mobileShadowingChunks;
  final bool mobileShadowingPracticeLoop;
  final bool mobileLoginRequired;
  final bool mobileAccessWaitingUx;
  final bool progressFailClosed;
  final bool figRefHints;
  // design/130 — missing key → on; explicit false kills client reporting.
  final bool cloudErrorLogs;
  final bool mobileCloudErrorLogs;
  // design/131 — missing → full; explicit false restores 2-line ellipsis.
  final bool captionFullText;
  // design/132 — missing → on; explicit false hides cancel.
  final bool mobileIngestCancel;
  // design/134 — upload/ingest no-progress hang.
  final bool mobileIngestUploadHang;
  final int ingestHangStallSeconds;
  // design/148 — mobile References panel kill switch.
  final bool mobileCiteRefPanel;
  // design/157 — Title section this-paper row kill switch.
  final bool mobileThisPaperPanel;
  final bool citeRefOpen;
  // design/149 — composite PNG; hide under-image caption when true.
  final bool figureCaptionInImage;
  final bool mobileFigureCaptionInImage;
  final bool bookmarksSync;
  final bool annotationsSync;
  /// design/161 — public GCS APK URL when configured on server.
  final String mobileApkUrl;
  /// design/169 — agent evidence bus (no UI).
  final bool evidenceBus;
}

/// `/api/bookmarks/sync` result.
class BookmarksSyncResult {
  const BookmarksSyncResult({
    required this.available,
    this.store,
    this.needsAuth = false,
    this.message,
  });

  final bool available;
  final Map<String, dynamic>? store;
  final bool needsAuth;
  final String? message;
}

/// `/api/annotations/sync` result (design/166).
class AnnotationsSyncResult {
  const AnnotationsSyncResult({
    required this.available,
    this.store,
    this.needsAuth = false,
    this.message,
  });

  final bool available;
  final Map<String, dynamic>? store;
  final bool needsAuth;
  final String? message;
}

/// `/api/cite/resolve` result (design/41 · 148).
class CiteResolveResult {
  CiteResolveResult({
    required this.ok,
    this.url = '',
    this.source = '',
    this.doi = '',
    this.title = '',
    this.error = '',
    this.message = '',
  });

  factory CiteResolveResult.fromJson(Map<String, dynamic> json) {
    return CiteResolveResult(
      ok: json['ok'] == true,
      url: '${json['url'] ?? ''}'.trim(),
      source: '${json['source'] ?? ''}'.trim(),
      doi: '${json['doi'] ?? ''}'.trim(),
      title: '${json['title'] ?? ''}'.trim(),
      error: '${json['error'] ?? ''}'.trim(),
      message: '${json['message'] ?? ''}'.trim(),
    );
  }

  final bool ok;
  final String url;
  final String source;
  final String doi;
  final String title;
  final String error;
  final String message;
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

  void _breadcrumbApiFail(String route, int status, String message) {
    // WHY: evidence POST fail must not recurse into evidence emit.
    final r = route.trim().toLowerCase();
    if (r.contains('evidence')) return;
    final msg = message.length > 200 ? message.substring(0, 200) : message;
    asrEvidenceBus?.record(
      status == 504 ? 'client_api_timeout' : 'client_api_fail',
      severity: 'error',
      route: route,
      httpStatus: status,
      message: msg,
      ok: false,
    );
  }

  /// design/169c — TimeoutException must carry a stable snake route.
  void _breadcrumbTimeout(String route, Object error) {
    final r = route.trim().toLowerCase();
    if (r.contains('evidence')) return;
    final msg = error.toString();
    asrEvidenceBus?.record(
      'client_api_timeout',
      severity: 'error',
      route: route,
      message: msg.length > 200 ? msg.substring(0, 200) : msg,
      ok: false,
      code: 'timeout',
    );
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
      _breadcrumbApiFail(label, res.statusCode, detail);
      throw AsrApiException(detail, res.statusCode);
    }
    final body = jsonDecode(res.body);
    if (body is! Map<String, dynamic>) {
      if (body is Map) {
        return Map<String, dynamic>.from(body);
      }
      _breadcrumbApiFail(label, res.statusCode, '$label body is not a JSON object');
      throw AsrApiException('$label body is not a JSON object', res.statusCode);
    }
    return body;
  }

  /// GET /api/status — health / version probe for the home shell.
  Future<AsrStatus> fetchStatus() async {
    try {
      final res = await _http
          .get(_uri('/api/status'), headers: await _headers())
          .timeout(const Duration(seconds: 20));
      final map = _decodeObject(res, 'status');
      return AsrStatus.fromJson(map);
    } on TimeoutException catch (e) {
      _breadcrumbTimeout('status', e);
      rethrow;
    }
  }

  /// GET /api/auth/status — session restore / provider flags.
  ///
  /// design/0.3.123 — 45s (cold start / Cloud Run busy); other APIs stay 20s.
  Future<AsrAuthStatus> fetchAuthStatus() async {
    try {
      final res = await _http
          .get(_uri('/api/auth/status'), headers: await _headers())
          .timeout(const Duration(seconds: 45));
      await _captureSession(res);
      final map = _decodeObject(res, 'auth_status');
      return AsrAuthStatus.fromJson(map);
    } on TimeoutException catch (e) {
      _breadcrumbTimeout('auth_status', e);
      rethrow;
    }
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

  /// Persist a session token from Kakao / magic mobile deep link (no Set-Cookie path).
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

  /// POST /api/auth/unlink — design/146a · session uid only (no body user_id).
  Future<AsrUser> unlinkProvider(String provider) async {
    final p = provider.trim().toLowerCase();
    if (p.isEmpty) {
      throw AsrApiException('invalid', 400);
    }
    final res = await _http
        .post(
          _uri('/api/auth/unlink'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'provider': p}),
        )
        .timeout(const Duration(seconds: 30));
    await _captureSession(res);
    final map = _decodeObject(res, 'auth/unlink');
    final userRaw = map['user'];
    final user = AsrUser.fromJson(
      userRaw is Map ? Map<String, dynamic>.from(userRaw) : null,
    );
    if (user.isEmpty) {
      throw AsrApiException('unlink returned empty user', res.statusCode);
    }
    return user;
  }

  /// Authenticated Kakao link start — Cookie required (Custom Tab has none).
  ///
  /// WHY: GET …/kakao/start?mode=link embeds link_uid in OAuth state from session.
  /// Returns the authorize URL (Location) without following the redirect.
  Future<String> resolveKakaoLinkAuthorizeUrl() async {
    final req = http.Request(
      'GET',
      _uri('/api/auth/kakao/start').replace(
        queryParameters: const {'mode': 'link', 'mobile': '1'},
      ),
    );
    // WHY: default followRedirects=true would consume 302 and hide Location.
    req.followRedirects = false;
    req.headers.addAll(await _headers());
    // WHY: Client.send honors Request.followRedirects — we need Location only.
    final streamed = await _http.send(req).timeout(const Duration(seconds: 30));
    final res = await http.Response.fromStream(streamed);
    if (res.statusCode == 401) {
      throw AsrApiException('연결하려면 먼저 로그인하세요.', 401);
    }
    if (res.statusCode == 503) {
      throw AsrApiException('카카오 연결이 꺼져 있습니다.', 503);
    }
    if (res.statusCode != 302 && res.statusCode != 301) {
      throw AsrApiException(
        '카카오 연결을 시작할 수 없습니다.',
        res.statusCode,
      );
    }
    final loc = (res.headers['location'] ?? '').trim();
    if (loc.isEmpty) {
      throw AsrApiException('카카오 연결 주소가 없습니다.', 502);
    }
    if (loc.startsWith('http://') || loc.startsWith('https://')) {
      return loc;
    }
    return _uri(loc).toString();
  }

  /// POST /api/auth/email/magic/request with intent=link (design/146a).
  Future<String> requestEmailLinkMagic({required String email}) async {
    final res = await _http
        .post(
          _uri('/api/auth/email/magic/request'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'email': email.trim(),
            'client': 'android',
            'intent': 'link',
          }),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'email/magic/request');
    if (map['ok'] != true) {
      throw AsrApiException(
        '${map['message'] ?? map['error'] ?? 'magic_request_failed'}',
        res.statusCode,
      );
    }
    return '${map['message'] ?? '연결 링크를 이메일로 보냈습니다.'}';
  }

  /// POST /api/auth/email/magic/request — SMTP send; no session yet (design/77).
  /// [client] ``android`` appends ``mobile=1`` so open deep-links the app (design/85).
  Future<String> requestMagicLink({required String email}) async {
    final res = await _http
        .post(
          _uri('/api/auth/email/magic/request'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'email': email.trim(),
            'client': 'android',
          }),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'email/magic/request');
    if (map['ok'] != true) {
      throw AsrApiException(
        '${map['message'] ?? map['error'] ?? 'magic_request_failed'}',
        res.statusCode,
      );
    }
    return '${map['message'] ?? '로그인 링크를 이메일로 보냈습니다.'}';
  }

  /// Absolute URL for Google Custom-Tab GIS start (mobile; design/65).
  String googleMobileStartUrl({String mode = 'login'}) {
    final m = mode.trim().isEmpty ? 'login' : mode.trim();
    return _uri('/api/auth/google/mobile/start').replace(
      queryParameters: {'mode': m},
    ).toString();
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
        .timeout(const Duration(seconds: 60));
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

  /// DELETE /api/cache/papers/{id} — local + GCS paper + user records (design/102).
  Future<void> deletePaper(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final res = await _http
        .delete(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 60));
    if (res.statusCode == 404) {
      throw AsrApiException('삭제할 보관본을 찾지 못했습니다.', 404);
    }
    final map = _decodeObject(res, 'cache/delete');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? '삭제에 실패했습니다.'}',
        res.statusCode,
      );
    }
  }

  /// POST /api/cache/papers/{id}/extend-retention — design/144 (+90d in warn window).
  Future<void> extendPaperRetention(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/extend-retention'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 409) {
      throw AsrApiException('지금은 연장할 수 없습니다.', 409);
    }
    if (res.statusCode == 404) {
      throw AsrApiException('보관본을 찾지 못했습니다.', 404);
    }
    final map = _decodeObject(res, 'cache/extend-retention');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? '연장에 실패했습니다.'}',
        res.statusCode,
      );
    }
  }

  /// POST /api/cache/papers/{id}/reanalyze — design/145 · design/20.
  Future<({String jobId, String cacheId})> startReanalyze(
    String cacheId, {
    bool translate = true,
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final q = translate ? '?translate=1' : '?translate=0';
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/reanalyze$q'),
          headers: await _headers(jsonBody: true),
          body: '{}',
        )
        .timeout(const Duration(seconds: 120));
    if (res.statusCode == 404) {
      throw AsrApiException(
        '원본 파일이 없어 재분석할 수 없습니다.',
        404,
      );
    }
    final map = _decodeObject(res, 'cache/reanalyze');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? '재분석을 시작하지 못했습니다.'}',
        res.statusCode,
      );
    }
    final jobId = '${map['job_id'] ?? ''}'.trim();
    final cid = '${map['cache_id'] ?? id}'.trim();
    if (jobId.isEmpty) {
      throw AsrApiException('작업 ID를 받지 못했습니다.', 500);
    }
    asrEvidenceBus?.adoptJobTrace('${map['trace_id'] ?? ''}');
    asrEvidenceBus?.record(
      'reanalyze_start',
      severity: 'lifecycle',
      stage: 'ok',
      jobId: jobId,
      cacheId: cid,
      ok: true,
      details: {'want_translate_sent': translate},
    );
    return (jobId: jobId, cacheId: cid);
  }

  /// POST /api/cache/papers/{id}/merge-supplementary — design/152.
  Future<Map<String, dynamic>> mergeSupplementary(String mainCacheId) async {
    final id = mainCacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final res = await _http
        .post(
          _uri(
            '/api/cache/papers/${Uri.encodeComponent(id)}/merge-supplementary',
          ),
          headers: await _headers(jsonBody: true),
          body: '{}',
        )
        .timeout(const Duration(seconds: 120));
    final map = _decodeObject(res, 'cache/merge-supplementary');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? '보충자료 합치기에 실패했습니다.'}',
        res.statusCode,
      );
    }
    return map;
  }

  /// GET /api/cache/papers/{id}/layout_map — design/151 overlay boxes.
  Future<Map<String, dynamic>> fetchLayoutMap(String cacheId) async {
    final id = cacheId.trim();
    final res = await _http
        .get(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/layout_map'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 60));
    final map = _decodeObject(res, 'cache/layout_map');
    if (map['ok'] == false) {
      throw AsrApiException('${map['message'] ?? 'layout_map failed'}', res.statusCode);
    }
    return Map<String, dynamic>.from(map['layout_map'] as Map? ?? {});
  }

  /// GET /api/cache/papers/{id}/slot_plan — design/151 slot carousel plan.
  Future<Map<String, dynamic>> fetchSlotPlan(String cacheId) async {
    final id = cacheId.trim();
    final res = await _http
        .get(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/slot_plan'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 60));
    final map = _decodeObject(res, 'cache/slot_plan');
    if (map['ok'] == false) {
      throw AsrApiException('${map['message'] ?? 'slot_plan failed'}', res.statusCode);
    }
    return Map<String, dynamic>.from(map['slot_plan'] as Map? ?? {});
  }

  /// POST assign body/caption box to slot — design/151 overlay editor.
  Future<void> assignSlot(
    String cacheId,
    String slotKey, {
    String? bodyBoxId,
    String? captionBoxId,
    String? captionText,
  }) async {
    final id = cacheId.trim();
    final sk = Uri.encodeComponent(slotKey.trim());
    final body = <String, dynamic>{};
    if (bodyBoxId != null && bodyBoxId.trim().isNotEmpty) {
      body['body_box_id'] = bodyBoxId.trim();
    }
    if (captionBoxId != null && captionBoxId.trim().isNotEmpty) {
      body['caption_box_id'] = captionBoxId.trim();
    }
    if (captionText != null && captionText.trim().isNotEmpty) {
      body['caption_text'] = captionText.trim();
    }
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/slots/$sk/assign'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 90));
    final map = _decodeObject(res, 'cache/slot/assign');
    if (map['ok'] == false) {
      throw AsrApiException('${map['message'] ?? 'assign failed'}', res.statusCode);
    }
  }

  /// POST re-render slot PNG after assign — design/151.
  Future<void> renderSlot(String cacheId, String slotKey) async {
    final id = cacheId.trim();
    final sk = Uri.encodeComponent(slotKey.trim());
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/slots/$sk/render'),
          headers: await _headers(jsonBody: true),
          body: '{}',
        )
        .timeout(const Duration(seconds: 120));
    final map = _decodeObject(res, 'cache/slot/render');
    if (map['ok'] == false) {
      throw AsrApiException('${map['message'] ?? 'render failed'}', res.statusCode);
    }
  }

  /// HEAD /api/cache/papers/{id}/source — design/163-E.
  Future<({String contentHash, int contentLength, String filename})?>
      headPaperSource(String cacheId) async {
    final id = cacheId.trim();
    final res = await _http
        .head(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/source'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 60));
    if (res.statusCode == 404) return null;
    if (res.statusCode == 413) {
      throw AsrApiException('원본이 너무 큽니다.', 413);
    }
    if (res.statusCode != 200) {
      throw AsrApiException('원본 정보를 가져오지 못했습니다.', res.statusCode);
    }
    final hash = res.headers['x-content-hash'] ?? '';
    final len = int.tryParse(res.headers['content-length'] ?? '') ?? 0;
    final name = res.headers['x-source-filename'] ?? 'source.pdf';
    return (contentHash: hash, contentLength: len, filename: name);
  }

  /// GET /api/cache/papers/{id}/source — design/163-E.
  Future<Uint8List> fetchPaperSourceBytes(String cacheId) async {
    final id = cacheId.trim();
    final res = await _http
        .get(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/source'),
          headers: await _headers(),
        )
        .timeout(const Duration(minutes: 3));
    if (res.statusCode == 404) {
      throw AsrApiException('원본이 없습니다.', 404);
    }
    if (res.statusCode == 413) {
      throw AsrApiException('원본이 너무 큽니다.', 413);
    }
    if (res.statusCode != 200) {
      throw AsrApiException('원본을 받지 못했습니다.', res.statusCode);
    }
    if (res.bodyBytes.isEmpty) {
      throw AsrApiException('원본이 비어 있습니다.', 500);
    }
    return res.bodyBytes;
  }

  /// GET /api/cache/papers/{id}/page_preview?page_index=N — design/163.
  Future<Uint8List> fetchPagePreview(String cacheId, int pageIndex) async {
    final id = cacheId.trim();
    final res = await _http
        .get(
          _uri(
            '/api/cache/papers/${Uri.encodeComponent(id)}/page_preview'
            '?page_index=$pageIndex',
          ),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 90));
    if (res.statusCode == 404) {
      throw AsrApiException('페이지 미리보기를 받지 못했습니다.', 404);
    }
    if (res.statusCode != 200) {
      throw AsrApiException('페이지 미리보기 실패', res.statusCode);
    }
    if (res.bodyBytes.isEmpty) {
      throw AsrApiException('빈 페이지 이미지', 500);
    }
    return res.bodyBytes;
  }

  /// POST multipart figure_edit commit — design/163.
  Future<void> commitFigureEdit({
    required String cacheId,
    required Map<String, dynamic> layoutMap,
    required Map<String, dynamic> slotPlan,
    required List<({
      String slotKey,
      String caption,
      int? pageIndex,
      Uint8List png,
    })> figures,
  }) async {
    final id = cacheId.trim();
    final manifest = {
      'layout_map': layoutMap,
      'slot_plan': slotPlan,
      'figures': [
        for (var i = 0; i < figures.length; i++)
          {
            'slot_key': figures[i].slotKey,
            'caption': figures[i].caption,
            'page_index': figures[i].pageIndex,
            'file_field': 'slot_$i',
          },
      ],
    };
    final req = http.MultipartRequest(
      'POST',
      _uri('/api/cache/papers/${Uri.encodeComponent(id)}/figure_edit/commit'),
    );
    final headers = await _headers();
    headers.remove('Content-Type');
    req.headers.addAll(headers);
    req.fields['manifest'] = jsonEncode(manifest);
    for (var i = 0; i < figures.length; i++) {
      req.files.add(
        http.MultipartFile.fromBytes(
          'slot_$i',
          figures[i].png,
          filename: '${figures[i].slotKey.replaceAll(':', '_')}.png',
        ),
      );
    }
    final streamed = await req.send().timeout(const Duration(minutes: 3));
    final res = await http.Response.fromStream(streamed);
    final map = _decodeObject(res, 'figure_edit/commit');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? 'commit failed'}',
        res.statusCode,
      );
    }
  }

  static final _pdfNameRe = RegExp(r'\.pdf$', caseSensitive: false);
  static const _maxUploadBytes = 50 * 1024 * 1024;

  /// POST /api/ingest (multipart `file`) then poll `/api/ingest/jobs/{id}`.
  ///
  void _validatePdfBytes(String filename, Uint8List bytes) {
    final name = filename.trim();
    if (name.isEmpty) {
      throw AsrApiException('파일 이름이 비어 있습니다.', 400);
    }
    if (!_pdfNameRe.hasMatch(name)) {
      throw AsrApiException('PDF만 업로드할 수 있습니다.', 400);
    }
    if (bytes.isEmpty) {
      throw AsrApiException('빈 파일입니다.', 400);
    }
    if (bytes.length > _maxUploadBytes) {
      throw AsrApiException('파일이 너무 큽니다 (최대 50MB).', 413);
    }
    if (bytes.length < 5 ||
        bytes[0] != 0x25 ||
        bytes[1] != 0x50 ||
        bytes[2] != 0x44 ||
        bytes[3] != 0x46) {
      throw AsrApiException('유효한 PDF가 아닙니다.', 400);
    }
  }

  /// design/72 — create chunked upload session for [contentHash]/[size].
  Future<({String uploadId, int chunkSize, int receivedOffset, String prefixSha256})>
      createChunkedUpload({
    required String filename,
    required String contentHash,
    required int size,
  }) async {
    final token = await _sessions.readToken();
    if (token == null || token.isEmpty) {
      throw AsrApiException('로그인이 필요합니다.', 401);
    }
    final res = await _http
        .post(
          _uri('/api/ingest/uploads'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'filename': filename.trim(),
            'content_hash': contentHash.trim().toLowerCase(),
            'size': size,
          }),
        )
        .timeout(const Duration(seconds: 30));
    await _captureSession(res);
    final map = _decodeObject(res, 'ingest/uploads');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? '업로드 세션 실패'}',
        res.statusCode,
      );
    }
    final uploadId = '${map['upload_id'] ?? ''}'.trim();
    if (!RegExp(r'^upl_[a-f0-9]{12}$').hasMatch(uploadId)) {
      throw AsrApiException('업로드 ID를 받지 못했습니다.', 500);
    }
    final chunkSize =
        map['chunk_size'] is num ? (map['chunk_size'] as num).toInt() : 262144;
    final offset = map['received_offset'] is num
        ? (map['received_offset'] as num).toInt()
        : 0;
    return (
      uploadId: uploadId,
      chunkSize: chunkSize > 0 ? chunkSize : 262144,
      receivedOffset: offset < 0 ? 0 : offset,
      prefixSha256: '${map['prefix_sha256'] ?? ''}'.trim().toLowerCase(),
    );
  }

  /// GET upload session for integrity probe before resume.
  Future<
      ({
        int receivedOffset,
        String prefixSha256,
        String contentHash,
        int size,
        int chunkSize,
      })> getChunkedUpload(String uploadId) async {
    final id = uploadId.trim();
    if (!RegExp(r'^upl_[a-f0-9]{12}$').hasMatch(id)) {
      throw AsrApiException('잘못된 업로드 ID입니다.', 400);
    }
    final res = await _http
        .get(
          _uri('/api/ingest/uploads/${Uri.encodeComponent(id)}'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 404) {
      throw AsrApiException('업로드 세션을 찾을 수 없습니다.', 404);
    }
    final map = _decodeObject(res, 'ingest/uploads/get');
    final cs =
        map['chunk_size'] is num ? (map['chunk_size'] as num).toInt() : 262144;
    return (
      receivedOffset: map['received_offset'] is num
          ? (map['received_offset'] as num).toInt()
          : 0,
      prefixSha256: '${map['prefix_sha256'] ?? ''}'.trim().toLowerCase(),
      contentHash: '${map['content_hash'] ?? ''}'.trim().toLowerCase(),
      size: map['size'] is num ? (map['size'] as num).toInt() : 0,
      chunkSize: cs > 0 ? cs : 262144,
    );
  }

  /// PUT one contiguous chunk at [offset].
  Future<int> putChunkedUpload({
    required String uploadId,
    required int offset,
    required Uint8List chunk,
    required String chunkSha256,
  }) async {
    final id = uploadId.trim();
    final res = await _http
        .put(
          _uri('/api/ingest/uploads/${Uri.encodeComponent(id)}')
              .replace(queryParameters: {'offset': '$offset'}),
          headers: {
            ...await _headers(),
            'Content-Type': 'application/octet-stream',
            'X-Chunk-Sha256': chunkSha256,
          },
          body: chunk,
        )
        .timeout(const Duration(seconds: 60));
    if (res.statusCode == 429) {
      // design/73 — surface server copy; never pretend chunk succeeded.
      throw AsrApiException('요청이 너무 많습니다.', 429);
    }
    if (res.statusCode == 409 || res.statusCode == 400) {
      throw AsrApiException('조각 무결성 검사에 실패했습니다. 다시 올려 주세요.', res.statusCode);
    }
    final map = _decodeObject(res, 'ingest/uploads/put');
    return map['received_offset'] is num
        ? (map['received_offset'] as num).toInt()
        : offset + chunk.length;
  }

  /// Assemble + start ingest job from a completed chunk session.
  Future<({String jobId, String contentHash})> completeChunkedUpload(
    String uploadId, {
    bool shadowingPractice = false,
    bool translate = true,
  }) async {
    final id = uploadId.trim();
    final q = _ingestOptQuery(
      shadowingPractice: shadowingPractice,
      translate: translate,
    );
    final res = await _http
        .post(
          _uri('/api/ingest/uploads/${Uri.encodeComponent(id)}/complete$q'),
          headers: await _headers(jsonBody: true),
          body: '{}',
        )
        .timeout(const Duration(seconds: 120));
    final map = _decodeObject(res, 'ingest/uploads/complete');
    if (map['ok'] == false) {
      throw AsrApiException(
        '${map['message'] ?? '업로드 완료 처리 실패'}',
        res.statusCode,
      );
    }
    final jobId = '${map['job_id'] ?? ''}'.trim();
    if (jobId.isEmpty) {
      throw AsrApiException('작업 ID를 받지 못했습니다.', 500);
    }
    asrEvidenceBus?.adoptJobTrace('${map['trace_id'] ?? ''}');
    return (
      jobId: jobId,
      contentHash: '${map['content_hash'] ?? ''}'.trim().toLowerCase(),
    );
  }

  /// design/72 — all PDFs: chunked put → complete → returns job_id.
  ///
  /// [existingUploadId]: resume after integrity check (caller verified prefix).
  Future<({String jobId, String contentHash, String uploadId})>
      startIngestPdfBytesChunked({
    required String filename,
    required Uint8List bytes,
    required String contentHash,
    String? existingUploadId,
    void Function(int percent, String message)? onProgress,
    Future<void> Function(String uploadId)? onUploadId,
    bool shadowingPractice = false,
    bool translate = true,
    bool Function()? isCancelled,
  }) async {
    _validatePdfBytes(filename, bytes);
    final token = await _sessions.readToken();
    if (token == null || token.isEmpty) {
      throw AsrApiException('로그인이 필요합니다.', 401);
    }

    var uploadId = (existingUploadId ?? '').trim();
    var offset = 0;
    var chunkSize = 262144;
    if (uploadId.isNotEmpty) {
      final st = await getChunkedUpload(uploadId);
      // EDGE: server session must match this file — else caller should have wiped.
      if (st.contentHash != contentHash.toLowerCase() || st.size != bytes.length) {
        throw AsrApiException('업로드 세션이 파일과 맞지 않습니다.', 409);
      }
      offset = st.receivedOffset;
      chunkSize = st.chunkSize;
      if (offset > 0) {
        final prefix = bytes.sublist(0, offset);
        final localPrefix = sha256Hex(prefix);
        if (localPrefix != st.prefixSha256) {
          // WHY (product): resume only after prior chunk integrity OK.
          throw AsrApiException('이전 조각 무결성 검사에 실패했습니다.', 409);
        }
      }
      if (onUploadId != null) await onUploadId(uploadId);
    } else {
      final created = await createChunkedUpload(
        filename: filename,
        contentHash: contentHash,
        size: bytes.length,
      );
      uploadId = created.uploadId;
      chunkSize = created.chunkSize;
      offset = created.receivedOffset;
      // WHY: persist upload_id before first PUT so kill mid-transfer can resume.
      if (onUploadId != null) await onUploadId(uploadId);
    }

    while (offset < bytes.length) {
      // design/132 — abort mid-chunk loop when user cancels.
      if (isCancelled?.call() == true) {
        throw UploadCancelledException();
      }
      final end = (offset + chunkSize > bytes.length)
          ? bytes.length
          : offset + chunkSize;
      final chunk = bytes.sublist(offset, end);
      final chunkHash = sha256Hex(chunk);
      offset = await putChunkedUpload(
        uploadId: uploadId,
        offset: offset,
        chunk: chunk,
        chunkSha256: chunkHash,
      );
      final pct = ((offset * 40) / bytes.length).floor().clamp(0, 40);
      onProgress?.call(pct, '조각 올리는 중');
    }

    if (isCancelled?.call() == true) {
      throw UploadCancelledException();
    }
    onProgress?.call(45, '조각 조립 · 처리 시작');
    final done = await completeChunkedUpload(
      uploadId,
      shadowingPractice: shadowingPractice,
      translate: translate,
    );
    return (
      jobId: done.jobId,
      contentHash: done.contentHash.isEmpty ? contentHash : done.contentHash,
      uploadId: uploadId,
    );
  }

  static String sha256Hex(List<int> bytes) =>
      sha256.convert(bytes).toString();

  /// Legacy multipart start (web-compat / kill-switch fallback).
  Future<({String jobId, String contentHash})> startIngestPdfBytes({
    required String filename,
    required Uint8List bytes,
    bool shadowingPractice = false,
    bool translate = true,
  }) async {
    _validatePdfBytes(filename, bytes);

    final token = await _sessions.readToken();
    if (token == null || token.isEmpty) {
      throw AsrApiException('로그인이 필요합니다.', 401);
    }

    final ingestPath =
        '/api/ingest${_ingestOptQuery(shadowingPractice: shadowingPractice, translate: translate)}';
    final req = http.MultipartRequest('POST', _uri(ingestPath));
    req.headers['Cookie'] = '$kAsrSessionCookieName=$token';
    req.headers['Accept'] = 'application/json';
    req.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename.trim()),
    );

    final streamed =
        await _http.send(req).timeout(const Duration(minutes: 3));
    final startRes = await http.Response.fromStream(streamed);
    await _captureSession(startRes);
    final start = _decodeObject(startRes, 'ingest');
    if (start['ok'] == false) {
      throw AsrApiException(
        '${start['message'] ?? '업로드에 실패했습니다.'}',
        startRes.statusCode,
      );
    }
    final jobId = '${start['job_id'] ?? ''}'.trim();
    if (jobId.isEmpty) {
      throw AsrApiException('작업 ID를 받지 못했습니다.', 500);
    }
    asrEvidenceBus?.adoptJobTrace('${start['trace_id'] ?? ''}');
    final hash = '${start['content_hash'] ?? ''}'.trim().toLowerCase();
    return (jobId: jobId, contentHash: hash);
  }

  /// Poll `/api/ingest/jobs/{id}` until done (design/71 reattach).
  ///
  /// design/158 — [idleTimeout] resets on each server percent/message change;
  /// [maxDuration] is an absolute safety cap (replaces fixed 20m wall clock).
  Future<IngestJobResult> pollIngestJob({
    required String jobId,
    void Function(int percent, String message)? onProgress,
    Duration pollInterval = const Duration(milliseconds: 500),
    Duration idleTimeout = const Duration(minutes: 5),
    Duration maxDuration = const Duration(hours: 2),
    bool Function()? isCancelled,
  }) async {
    final jid = jobId.trim();
    if (jid.isEmpty || !RegExp(r'^job_[a-f0-9]{12}$').hasMatch(jid)) {
      throw AsrApiException('잘못된 작업 ID입니다.', 400);
    }
    final absoluteDeadline = DateTime.now().add(maxDuration);
    var idleDeadline = DateTime.now().add(idleTimeout);
    var lastPct = -1;
    var lastMsg = '';
    while (DateTime.now().isBefore(absoluteDeadline)) {
      if (DateTime.now().isAfter(idleDeadline)) {
        _breadcrumbApiFail(
          'ingest/jobs/poll',
          504,
          '분석 진행이 멈춘 것 같습니다. 아래 「이어서 분석하기」를 눌러 주세요.',
        );
        throw AsrApiException(
          '분석 진행이 멈춘 것 같습니다. 아래 「이어서 분석하기」를 눌러 주세요.',
          504,
        );
      }
      // design/132 — stop polling after user cancel (server wipe → 404 is OK).
      if (isCancelled?.call() == true) {
        throw UploadCancelledException();
      }
      await Future<void>.delayed(pollInterval);
      if (isCancelled?.call() == true) {
        throw UploadCancelledException();
      }
      final stRes = await _http
          .get(
            _uri('/api/ingest/jobs/${Uri.encodeComponent(jid)}'),
            headers: await _headers(),
          )
          .timeout(const Duration(seconds: 30));
      if (stRes.statusCode == 401) {
        _breadcrumbApiFail('ingest/jobs', 401, '로그인이 필요합니다.');
        throw AsrApiException('로그인이 필요합니다.', 401);
      }
      if (stRes.statusCode == 404) {
        // EDGE: after cancel wipe, 404 is expected — treat as cancelled if flagged.
        if (isCancelled?.call() == true) {
          throw UploadCancelledException();
        }
        // EDGE: job lost even after GCS — fail-closed, no fake success.
        _breadcrumbApiFail('ingest/jobs', 404, '작업을 찾을 수 없습니다.');
        throw AsrApiException('작업을 찾을 수 없습니다. 다시 시도해 주세요.', 404);
      }
      if (stRes.statusCode < 200 || stRes.statusCode >= 300) {
        _breadcrumbApiFail('ingest/jobs', stRes.statusCode, '진행 상태 조회 실패');
        throw AsrApiException('진행 상태 조회 실패', stRes.statusCode);
      }
      final decoded = jsonDecode(stRes.body);
      if (decoded is! Map) {
        _breadcrumbApiFail('ingest/jobs', 500, '진행 상태 형식이 올바르지 않습니다.');
        throw AsrApiException('진행 상태 형식이 올바르지 않습니다.', 500);
      }
      final st = Map<String, dynamic>.from(decoded);
      final pct = st['percent'] is num ? (st['percent'] as num).toInt() : 0;
      final msg = '${st['message'] ?? ''}'.trim();
      final cacheId = '${st['cache_id'] ?? st['result_cache_id'] ?? ''}'.trim();
      // design/169g phase 5 — join mobile evidence to server job trace
      asrEvidenceBus?.adoptJobTrace('${st['trace_id'] ?? ''}');
      if (pct != lastPct || msg != lastMsg) {
        lastPct = pct;
        lastMsg = msg;
        idleDeadline = DateTime.now().add(idleTimeout);
        asrEvidenceBus?.record(
          'ingest_poll_tick',
          severity: 'lifecycle',
          jobId: jid,
          percent: pct,
          stage: msg.isEmpty ? 'poll' : (msg.length > 40 ? msg.substring(0, 40) : msg),
        );
        // design/169g phase 3 — UI clock for join with server handoff/call_*
        asrEvidenceBus?.record(
          'progress_view',
          severity: 'sample',
          jobId: jid,
          cacheId: cacheId,
          percent: pct,
          stage: 'poll',
          details: {
            'view_side': 'mobile',
            'msg_hash': _progressMsgHash(msg),
            'msg_len': msg.length.clamp(0, 1000000),
            if (st['done'] == true) 'job_done': true,
          },
        );
      }
      onProgress?.call(pct, msg);

      final done = st['done'] == true;
      if (!done) continue;

      // EDGE: failed job may still be HTTP 200 with ok:false.
      // design/109: 422 = terminal (clear resume draft); not 5xx/retryable poll blip.
      final sessionId = '${st['session_id'] ?? ''}'.trim();
      if (st['ok'] == false && sessionId.isEmpty) {
        final errCode = '${st['error'] ?? ''}'.trim();
        final detail = msg.isNotEmpty
            ? msg
            : (errCode.isNotEmpty && errCode != 'ingest_failed'
                ? errCode
                : '처리에 실패했습니다.');
        asrEvidenceBus?.record(
          'client_api_fail',
          severity: 'error',
          route: 'ingest/jobs/terminal',
          jobId: jid,
          httpStatus: 422,
          message: detail.length > 200 ? detail.substring(0, 200) : detail,
          ok: false,
          code: 'ingest_failed',
          percent: pct,
        );
        throw AsrApiException(
          detail,
          422,
        );
      }
      // WHY: library list is GCS/cache-backed — session_id alone is not durable.
      // EDGE: short-title skip finishes without cache_id — must not look like success.
      // design/108: avoid「보관 저장 실패: 완료」when server used bare「완료」.
      // cacheId already parsed above for progress_view each tick.
      if (cacheId.isEmpty) {
        final bareDone = msg.isEmpty || msg == '완료';
        final detail = bareDone
            ? '처리는 끝났지만 보관함에 저장되지 않았습니다. 제목이 너무 짧은 PDF일 수 있습니다.'
            : (msg.startsWith('보관') || msg.contains('보관함')
                ? msg
                : '보관 저장 실패: $msg');
        asrEvidenceBus?.record(
          'client_api_fail',
          severity: 'error',
          route: 'ingest/jobs/no_cache',
          jobId: jid,
          httpStatus: 422,
          message: detail.length > 200 ? detail.substring(0, 200) : detail,
          ok: false,
        );
        throw AsrApiException(
          detail,
          422,
        );
      }
      return IngestJobResult(
        jobId: jid,
        cacheId: cacheId,
        sessionId: sessionId,
        title: '${st['title'] ?? ''}'.trim(),
        percent: pct > 0 ? pct : 100,
        contentHash: '${st['content_hash'] ?? ''}'.trim().toLowerCase(),
      );
    }
    _breadcrumbApiFail(
      'ingest/jobs/poll',
      504,
      '전체 처리 시간이 너무 깁니다.',
    );
    throw AsrApiException(
      '전체 처리 시간이 너무 깁니다. 잠시 후 「이어서 분석하기」를 눌러 주세요.',
      504,
    );
  }

  /// Full ingest: chunked upload + poll (design/72). Falls back to multipart
  /// only when chunked create returns 503 (kill switch).
  Future<IngestJobResult> ingestPdfBytes({
    required String filename,
    required Uint8List bytes,
    void Function(int percent, String message)? onProgress,
    Duration pollInterval = const Duration(milliseconds: 500),
    Duration idleTimeout = const Duration(minutes: 5),
    Duration maxDuration = const Duration(hours: 2),
    String? existingUploadId,
    bool shadowingPractice = false,
    bool translate = true,
  }) async {
    _validatePdfBytes(filename, bytes);
    final hash = sha256Hex(bytes);
    late final String jobId;
    late final String contentHash;
    try {
      final started = await startIngestPdfBytesChunked(
        filename: filename,
        bytes: bytes,
        contentHash: hash,
        existingUploadId: existingUploadId,
        onProgress: onProgress,
        shadowingPractice: shadowingPractice,
        translate: translate,
      );
      jobId = started.jobId;
      contentHash = started.contentHash;
    } on AsrApiException catch (e) {
      // Kill switch / older server — multipart path.
      if (e.statusCode == 503) {
        final started =
            await startIngestPdfBytes(
          filename: filename,
          bytes: bytes,
          shadowingPractice: shadowingPractice,
          translate: translate,
        );
        jobId = started.jobId;
        contentHash = started.contentHash;
        onProgress?.call(1, '업로드 완료, 처리 중');
      } else {
        rethrow;
      }
    }
    onProgress?.call(50, '처리 중');
    final result = await pollIngestJob(
      jobId: jobId,
      onProgress: (pct, msg) {
        // Map server 0–100 into remaining half of bar after chunk phase.
        final mapped = 50 + (pct.clamp(0, 100) ~/ 2);
        onProgress?.call(mapped, msg);
      },
      pollInterval: pollInterval,
      idleTimeout: idleTimeout,
      maxDuration: maxDuration,
    );
    if (result.contentHash.isEmpty && contentHash.isNotEmpty) {
      return IngestJobResult(
        jobId: result.jobId,
        cacheId: result.cacheId,
        sessionId: result.sessionId,
        title: result.title,
        percent: result.percent,
        contentHash: contentHash,
      );
    }
    return result;
  }

  /// POST /api/cache/papers/{id}/open — start a reading session from cache.
  Future<ReadingSession> openPaper(
    String cacheId, {
    bool translate = true,
    bool translatePoll = false,
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final q = translate ? 'translate=1' : 'translate=0';
    final pollQ = translatePoll ? '&poll=1' : '';
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/open?$q$pollQ'),
          headers: await _headers(jsonBody: true),
          body: '{}',
        )
        .timeout(const Duration(seconds: 120));
    final map = _decodeObject(res, 'cache/open');
    final opened = ReadingSession.fromOpenJson(map);
    if (!opened.isValid) {
      throw AsrApiException('open returned empty session_id', res.statusCode);
    }
    // design/114 — refuse title-only opens (empty reader).
    // design/121 — server already refuses GCS pull failure; still guard empty payload.
    if (opened.sentenceCount < 1) {
      throw AsrApiException(
        '보관본에 문장이 없습니다. 재분석하거나 PDF를 다시 올려 주세요.',
        res.statusCode,
      );
    }
    return opened;
  }

  /// design/129 — GET /api/session/{id}/figures/window?center=&span=
  /// Returns figure rows plus optional server-side empty reason aggregates (169l L3).
  Future<({List<Map<String, dynamic>> figures, Map<String, int> serverEmptyReasons})>
      fetchFigureWindow({
    required String sessionId,
    required int center,
    int span = 1,
    String cacheId = '',
  }) async {
    final sid = sessionId.trim();
    if (sid.isEmpty) {
      throw AsrApiException('session id is empty', 400);
    }
    final cid = cacheId.trim();
    asrEvidenceBus?.record(
      'figure_window_req',
      severity: 'lifecycle',
      cacheId: cid,
      stage: 'req',
      details: {'center': center, 'span': span},
    );
    final cacheQ = cid.isEmpty
        ? ''
        : '&cache_id=${Uri.encodeQueryComponent(cid)}';
    try {
      final res = await _http
          .get(
            _uri(
              '/api/session/${Uri.encodeComponent(sid)}/figures/window'
              '?center=$center&span=$span$cacheQ',
            ),
            headers: await _headers(),
          )
          .timeout(const Duration(seconds: 90));
      final map = _decodeObject(res, 'figures_window');
      final raw = map['figures'];
      final reasonsRaw = map['empty_reasons'];
      final serverEmptyReasons = <String, int>{};
      if (reasonsRaw is Map) {
        for (final entry in reasonsRaw.entries) {
          final k = '${entry.key}'.trim();
          final v = entry.value;
          if (k.isEmpty) continue;
          if (v is int) {
            serverEmptyReasons[k] = v;
          } else if (v is num) {
            serverEmptyReasons[k] = v.toInt();
          }
        }
      }
      if (raw is! List) {
        return (figures: const <Map<String, dynamic>>[], serverEmptyReasons: serverEmptyReasons);
      }
      final out = <Map<String, dynamic>>[];
      for (final item in raw) {
        if (item is Map) {
          out.add(Map<String, dynamic>.from(item));
        }
      }
      return (figures: out, serverEmptyReasons: serverEmptyReasons);
    } on TimeoutException catch (e) {
      _breadcrumbTimeout('figures_window', e);
      rethrow;
    }
  }

  /// design/99 — ingest/open query flags (mobile always sends translate explicitly).
  static String _ingestOptQuery({
    bool shadowingPractice = false,
    bool translate = true,
  }) {
    final parts = <String>[
      if (shadowingPractice) 'shadowing_practice=1',
      translate ? 'translate=1' : 'translate=0',
    ];
    return '?${parts.join('&')}';
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
    try {
      final res = await _http
          .get(_uri('/api/access/status'), headers: await _headers())
          .timeout(const Duration(seconds: 20));
      final map = _decodeObject(res, 'access_status');
      return AccessStatus.fromJson(map);
    } on TimeoutException catch (e) {
      _breadcrumbTimeout('access_status', e);
      rethrow;
    }
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

  /// design/41 · 148 — bibliography row → publisher / Crossref / Scholar URL.
  Future<CiteResolveResult> resolveCite(String text) async {
    final res = await _http
        .post(
          _uri('/api/cite/resolve'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'text': text}),
        )
        .timeout(const Duration(seconds: 25));
    final map = _decodeObject(res, 'cite/resolve');
    return CiteResolveResult.fromJson(map);
  }

  void close() => _http.close();


  /// design/82 — GET per-uid practice takes.
  Future<Map<String, dynamic>> fetchShadowingTakes(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('논문 id가 올바르지 않습니다.', 400);
    }
    final res = await _http.get(
      _uri('/api/shadowing/takes/${Uri.encodeComponent(id)}'),
      headers: await _headers(),
    );
    return _decodeObject(res, 'shadowing/takes');
  }

  /// design/82 — save take or skip.
  Future<Map<String, dynamic>> postShadowingTake(
    String cacheId, {
    required bool practiceEnabled,
    required String sentenceId,
    required int chunkIndex,
    required int chunkCount,
    required String status,
    String? blobKey,
    String? mime,
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('논문 id가 올바르지 않습니다.', 400);
    }
    final body = <String, dynamic>{
      'practice_enabled': practiceEnabled,
      'action': 'take',
      'sentence_id': sentenceId,
      'chunk_index': chunkIndex,
      'chunk_count': chunkCount,
      'status': status,
      if (blobKey != null) 'blob_key': blobKey,
      if (mime != null) 'mime': mime,
    };
    final res = await _http.post(
      _uri('/api/shadowing/takes/${Uri.encodeComponent(id)}'),
      headers: {
        ...await _headers(),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(body),
    );
    return _decodeObject(res, 'shadowing/takes/post');
  }

  /// design/82 — full-pass continue playlist.
  Future<Map<String, dynamic>> continueShadowingTakes(
    String cacheId, {
    required bool practiceEnabled,
    required List<String> sentenceIds,
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('논문 id가 올바르지 않습니다.', 400);
    }
    final res = await _http.post(
      _uri('/api/shadowing/takes/${Uri.encodeComponent(id)}/continue'),
      headers: {
        ...await _headers(),
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'practice_enabled': practiceEnabled,
        'sentence_ids': sentenceIds,
      }),
    );
    return _decodeObject(res, 'shadowing/takes/continue');
  }

  /// Upload voice bytes (reuse design/17 voice blobs).
  Future<void> putVoiceBlob(String blobKey, List<int> bytes, {String? contentType}) async {
    final key = blobKey.trim();
    if (key.isEmpty) {
      throw AsrApiException('blob key가 올바르지 않습니다.', 400);
    }
    final res = await _http.put(
      _uri('/api/voice/blobs').replace(queryParameters: {'key': key}),
      headers: {
        ...await _headers(),
        'Content-Type': contentType ?? 'application/octet-stream',
      },
      body: bytes,
    );
    if (res.statusCode == 401) {
      throw AsrApiException('로그인이 필요합니다.', 401);
    }
    if (res.statusCode >= 400) {
      throw AsrApiException('녹음 업로드에 실패했습니다.', res.statusCode);
    }
  }

  /// design/80 — GET per-uid chunk plan.
  Future<Map<String, dynamic>> fetchShadowingChunks(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('논문 id가 올바르지 않습니다.', 400);
    }
    final res = await _http.get(
      _uri('/api/shadowing/chunks/${Uri.encodeComponent(id)}'),
      headers: await _headers(),
    );
    return _decodeObject(res, 'shadowing/chunks');
  }

  /// design/80 — backfill/retry (requires practiceEnabled true).
  /// design/113 — client timeout under Cloud Run limit so we can continue slices.
  Future<Map<String, dynamic>> buildShadowingChunks(
    String cacheId, {
    required bool practiceEnabled,
    List<Map<String, dynamic>>? sentences,
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('논문 id가 올바르지 않습니다.', 400);
    }
    final body = <String, dynamic>{
      'practice_enabled': practiceEnabled,
      if (sentences != null) 'sentences': sentences,
    };
    final res = await _http
        .post(
          _uri('/api/shadowing/chunks/${Uri.encodeComponent(id)}/build'),
          headers: {
            ...await _headers(),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 150));
    return _decodeObject(res, 'shadowing/chunks/build');
  }

  /// POST /api/errors/report — design/130 (fail quietly at call sites).
  Future<void> reportError({
    required String kind,
    required String message,
    String stack = '',
    String stage = '',
    String? paperTitle,
    String? cacheId,
    String platform = '',
    String appVersion = '',
  }) async {
    final res = await _http
        .post(
          _uri('/api/errors/report'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'kind': kind,
            'message': message,
            'stack': stack,
            'stage': stage,
            if (paperTitle != null && paperTitle.isNotEmpty)
              'paper_title': paperTitle,
            if (cacheId != null && cacheId.isNotEmpty) 'cache_id': cacheId,
            if (platform.isNotEmpty) 'platform': platform,
            if (appVersion.isNotEmpty) 'app_version': appVersion,
          }),
        )
        .timeout(const Duration(seconds: 20));
    _decodeObject(res, 'errors/report');
  }

  /// POST /api/evidence/ingest — design/169 (write-only; no GET).
  Future<({int accepted, int dropped})> postEvidenceBatch(
    List<Map<String, dynamic>> events,
  ) async {
    final batch = events.length > 50 ? events.sublist(0, 50) : events;
    final res = await _http
        .post(
          _uri('/api/evidence/ingest'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'events': batch}),
        )
        .timeout(const Duration(seconds: 20));
    // WHY: do not use _decodeObject — evidence fail must not breadcrumb recurse.
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw AsrApiException(
        'evidence ingest HTTP ${res.statusCode}',
        res.statusCode,
      );
    }
    final body = jsonDecode(res.body);
    if (body is! Map) {
      throw AsrApiException('evidence ingest bad body', res.statusCode);
    }
    final accepted = body['accepted'] is num ? (body['accepted'] as num).toInt() : 0;
    final dropped = body['dropped'] is num ? (body['dropped'] as num).toInt() : 0;
    return (accepted: accepted, dropped: dropped);
  }

  /// GET /api/errors/admin
  Future<List<Map<String, dynamic>>> fetchAdminErrorLogs({int limit = 50}) async {
    final res = await _http
        .get(
          _uri('/api/errors/admin').replace(queryParameters: {
            'limit': '$limit',
          }),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 30));
    final map = _decodeObject(res, 'errors/admin');
    final raw = map['events'];
    if (raw is! List) return const [];
    return [
      for (final item in raw)
        if (item is Map) Map<String, dynamic>.from(item),
    ];
  }

  /// GET /api/errors/admin/badge
  Future<int> fetchAdminErrorBadge() async {
    final res = await _http
        .get(_uri('/api/errors/admin/badge'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    final map = _decodeObject(res, 'errors/admin/badge');
    final n = map['count'];
    if (n is int) return n;
    if (n is num) return n.toInt();
    return 0;
  }

  /// POST /api/errors/admin/seen
  Future<void> markAdminErrorsSeen() async {
    final res = await _http
        .post(_uri('/api/errors/admin/seen'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    _decodeObject(res, 'errors/admin/seen');
  }

  /// design/132 — cancel early ingest job (owner session). 409 = too late.
  Future<({bool cancelled, bool tooLate})> cancelIngestJob(String jobId) async {
    final jid = jobId.trim();
    if (jid.isEmpty || !RegExp(r'^job_[a-f0-9]{12}$').hasMatch(jid)) {
      throw AsrApiException('잘못된 작업 ID입니다.', 400);
    }
    final res = await _http
        .post(
          _uri('/api/ingest/jobs/${Uri.encodeComponent(jid)}/cancel'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 401) {
      throw AsrApiException('로그인이 필요합니다.', 401);
    }
    if (res.statusCode == 409) {
      return (cancelled: false, tooLate: true);
    }
    if (res.statusCode == 404) {
      // Already wiped / unknown — treat as cancelled for local cleanup.
      return (cancelled: true, tooLate: false);
    }
    if (res.statusCode == 503) {
      throw AsrApiException('지금은 취소를 사용할 수 없습니다.', 503);
    }
    final map = _decodeObject(res, 'ingest/jobs/cancel');
    return (
      cancelled: map['cancelled'] == true || map['ok'] == true,
      tooLate: false,
    );
  }

  /// design/132 — discard chunked upload session before complete.
  Future<void> cancelChunkedUpload(String uploadId) async {
    final id = uploadId.trim();
    if (id.isEmpty || !RegExp(r'^upl_[a-f0-9]{12}$').hasMatch(id)) {
      throw AsrApiException('잘못된 업로드 ID입니다.', 400);
    }
    final res = await _http
        .post(
          _uri('/api/ingest/uploads/${Uri.encodeComponent(id)}/cancel'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 401) {
      throw AsrApiException('로그인이 필요합니다.', 401);
    }
    if (res.statusCode == 404) {
      return;
    }
    if (res.statusCode == 503) {
      throw AsrApiException('지금은 취소를 사용할 수 없습니다.', 503);
    }
    _decodeObject(res, 'ingest/uploads/cancel');
  }

  Future<BookmarksSyncResult> fetchBookmarksSync() async {
    final res = await _http
        .get(_uri('/api/bookmarks/sync'), headers: await _headers())
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 401) {
      return const BookmarksSyncResult(
        available: false,
        needsAuth: true,
        message: '로그인이 필요합니다.',
      );
    }
    final map = _decodeObject(res, 'bookmarks/sync');
    final store = map['store'];
    return BookmarksSyncResult(
      available: map['available'] == true,
      store: store is Map<String, dynamic>
          ? store
          : (store is Map ? Map<String, dynamic>.from(store) : null),
      needsAuth: map['needs_auth'] == true,
      message: map['message']?.toString(),
    );
  }

  Future<BookmarksSyncResult> pushBookmarksSync(Map<String, dynamic> store) async {
    final res = await _http
        .put(
          _uri('/api/bookmarks/sync'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'store': store}),
        )
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 401) {
      return const BookmarksSyncResult(
        available: false,
        needsAuth: true,
        message: '로그인이 필요합니다.',
      );
    }
    final map = _decodeObject(res, 'bookmarks/sync');
    final merged = map['store'];
    return BookmarksSyncResult(
      available: map['available'] == true,
      store: merged is Map<String, dynamic>
          ? merged
          : (merged is Map ? Map<String, dynamic>.from(merged) : null),
      needsAuth: map['needs_auth'] == true,
      message: map['message']?.toString(),
    );
  }

  Future<AnnotationsSyncResult> fetchAnnotationsSync() async {
    final res = await _http
        .get(_uri('/api/annotations/sync'), headers: await _headers())
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 401) {
      return const AnnotationsSyncResult(
        available: false,
        needsAuth: true,
        message: '로그인이 필요합니다.',
      );
    }
    final map = _decodeObject(res, 'annotations/sync');
    final store = map['store'];
    return AnnotationsSyncResult(
      available: map['available'] == true,
      store: store is Map<String, dynamic>
          ? store
          : (store is Map ? Map<String, dynamic>.from(store) : null),
      needsAuth: map['needs_auth'] == true,
      message: map['message']?.toString(),
    );
  }

  Future<AnnotationsSyncResult> pushAnnotationsSync(
    Map<String, dynamic> store,
  ) async {
    final res = await _http
        .put(
          _uri('/api/annotations/sync'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'store': store}),
        )
        .timeout(const Duration(seconds: 30));
    if (res.statusCode == 401) {
      return const AnnotationsSyncResult(
        available: false,
        needsAuth: true,
        message: '로그인이 필요합니다.',
      );
    }
    final map = _decodeObject(res, 'annotations/sync');
    final merged = map['store'];
    return AnnotationsSyncResult(
      available: map['available'] == true,
      store: merged is Map<String, dynamic>
          ? merged
          : (merged is Map ? Map<String, dynamic>.from(merged) : null),
      needsAuth: map['needs_auth'] == true,
      message: map['message']?.toString(),
    );
  }

}

class AsrApiException implements Exception {
  AsrApiException(this.message, [this.statusCode]);

  final String message;
  final int? statusCode;

  @override
  String toString() => 'AsrApiException($message, status=$statusCode)';
}

/// design/132 — user aborted upload/ingest; not a processing failure.
class UploadCancelledException implements Exception {
  @override
  String toString() => 'UploadCancelledException';
}
