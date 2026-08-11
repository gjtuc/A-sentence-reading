/// Thin HTTP client for the existing Cloud Run FastAPI surface.
///
/// Auth (email·Google·Kakao) · library · reader · TTS (0.2.75 · design/61-65).
///
/// WHY separate from UI: screens must not know cookie jars / timeouts;
/// cookie persistence stays in this layer (design/33).
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'auth_models.dart';
import 'paper_models.dart';
import 'reading_models.dart';
import 'session_store.dart';
import 'tts_models.dart';
import 'oauth_models.dart';
import 'access_models.dart';
import 'ingest_models.dart';

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
    final hash = '${start['content_hash'] ?? ''}'.trim().toLowerCase();
    return (jobId: jobId, contentHash: hash);
  }

  /// Poll `/api/ingest/jobs/{id}` until done (design/71 reattach).
  Future<IngestJobResult> pollIngestJob({
    required String jobId,
    void Function(int percent, String message)? onProgress,
    Duration pollInterval = const Duration(milliseconds: 500),
    Duration timeout = const Duration(minutes: 12),
  }) async {
    final jid = jobId.trim();
    if (jid.isEmpty || !RegExp(r'^job_[a-f0-9]{12}$').hasMatch(jid)) {
      throw AsrApiException('잘못된 작업 ID입니다.', 400);
    }
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
      final stRes = await _http
          .get(
            _uri('/api/ingest/jobs/${Uri.encodeComponent(jid)}'),
            headers: await _headers(),
          )
          .timeout(const Duration(seconds: 30));
      if (stRes.statusCode == 401) {
        throw AsrApiException('로그인이 필요합니다.', 401);
      }
      if (stRes.statusCode == 404) {
        // EDGE: job lost even after GCS — fail-closed, no fake success.
        throw AsrApiException('작업을 찾을 수 없습니다. 다시 시도해 주세요.', 404);
      }
      if (stRes.statusCode < 200 || stRes.statusCode >= 300) {
        throw AsrApiException('진행 상태 조회 실패', stRes.statusCode);
      }
      final decoded = jsonDecode(stRes.body);
      if (decoded is! Map) {
        throw AsrApiException('진행 상태 형식이 올바르지 않습니다.', 500);
      }
      final st = Map<String, dynamic>.from(decoded);
      final pct = st['percent'] is num ? (st['percent'] as num).toInt() : 0;
      final msg = '${st['message'] ?? ''}'.trim();
      onProgress?.call(pct, msg);

      final done = st['done'] == true;
      if (!done) continue;

      // EDGE: failed job may still be HTTP 200 with ok:false.
      final sessionId = '${st['session_id'] ?? ''}'.trim();
      if (st['ok'] == false && sessionId.isEmpty) {
        throw AsrApiException(
          msg.isEmpty ? '처리에 실패했습니다.' : msg,
          500,
        );
      }
      final cacheId = '${st['cache_id'] ?? ''}'.trim();
      // WHY: library list is GCS/cache-backed — session_id alone is not durable.
      // EDGE: short-title skip (`cache_skip_short_title`) finishes job with no cache_id
      // → must not show “보관에 추가됨” with an empty list (fail-closed).
      if (cacheId.isEmpty) {
        throw AsrApiException(
          msg.isEmpty
              ? '처리는 끝났지만 보관함에 저장되지 않았습니다. 제목이 너무 짧은 PDF일 수 있습니다.'
              : '보관 저장 실패: $msg',
          500,
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
    throw AsrApiException('업로드 처리 시간이 초과되었습니다.', 504);
  }

  /// Full ingest: chunked upload + poll (design/72). Falls back to multipart
  /// only when chunked create returns 503 (kill switch).
  Future<IngestJobResult> ingestPdfBytes({
    required String filename,
    required Uint8List bytes,
    void Function(int percent, String message)? onProgress,
    Duration pollInterval = const Duration(milliseconds: 500),
    Duration timeout = const Duration(minutes: 12),
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
      timeout: timeout,
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
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) {
      throw AsrApiException('cache id is empty', 400);
    }
    final q = translate ? '?translate=1' : '?translate=0';
    final res = await _http
        .post(
          _uri('/api/cache/papers/${Uri.encodeComponent(id)}/open$q'),
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
    final res = await _http.post(
      _uri('/api/shadowing/chunks/${Uri.encodeComponent(id)}/build'),
      headers: {
        ...await _headers(),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(body),
    );
    return _decodeObject(res, 'shadowing/chunks/build');
  }

}

class AsrApiException implements Exception {
  AsrApiException(this.message, [this.statusCode]);

  final String message;
  final int? statusCode;

  @override
  String toString() => 'AsrApiException($message, status=$statusCode)';
}
