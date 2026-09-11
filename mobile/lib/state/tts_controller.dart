/// Plays current sentence via Cloud TTS (design/64 · design/103).
///
/// Server synthesizes + GCS-caches MP3; this controller only fetches bytes
/// and feeds audioplayers. Live Enable / IPS stay out of ASR.
library;

import 'dart:math';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/cite_refs.dart' as cite;
import '../api/client.dart';
import '../api/tts_models.dart';
import '../services/evidence_bus.dart';
import 'library_controller.dart';

class TtsController extends ChangeNotifier {
  TtsController({
    required AsrClient client,
    required LibraryController library,
    AudioPlayer? player,
    SharedPreferences? prefs,
    Random? random,
  })  : _client = client,
        _library = library,
        _player = player ?? AudioPlayer(),
        _prefs = prefs,
        _random = random ?? Random() {
    _library.addListener(_onLibraryChanged);
    _player.onPlayerComplete.listen((_) {
      playing = false;
      notifyListeners();
    });
  }

  final AsrClient _client;
  final LibraryController _library;
  final AudioPlayer _player;
  final Random _random;
  SharedPreferences? _prefs;

  bool loading = false;
  bool playing = false;
  bool ready = false;
  bool voicesLoading = false;
  String? error;

  /// Client-side speed only (server caches native 1.0). Used in fixed mode.
  double rate = kTtsRateDefault;

  /// Fixed-mode voice; random modes ignore this per play.
  String voice = kTtsDefaultVoice;

  /// fixed | random_normal | random_hard | random_very_hard
  String mode = kTtsModeFixed;
  int skillTier = 2; // design/212

  /// Curated list from GET /api/tts/voices (may be empty until loaded).
  List<TtsVoiceChoice> voices = const [];

  bool get isRandomMode => isTtsRandomMode(mode);

  int? _lastSentenceIndex;
  String? _lastSessionId;

  /// design/219 — emit tts_auth_sticky at most once per sticky episode.
  bool _authStickyEmitted = false;

  Future<SharedPreferences> _readyPrefs() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  /// design/219 — red UI under reader chrome is this sticky auth fail string.
  bool get hasStickyAuthError {
    final e = (error ?? '').toLowerCase();
    if (e.isEmpty) return false;
    return e.contains('401') ||
        e.contains('auth_required') ||
        e.contains('login') ||
        e.contains('로그인');
  }

  Future<int> _hasSessionTokenFlag() async {
    try {
      final t = await _client.sessionStore.readToken();
      return (t != null && t.trim().isNotEmpty) ? 1 : 0;
    } catch (_) {
      return 0;
    }
  }

  /// Load persisted mode / voice / rate once at cold start.
  Future<void> bootstrap() async {
    try {
      final p = await _readyPrefs();
      final rawRate = p.getDouble(kTtsRatePrefsKey);
      rate = clampSpeakingRate(rawRate ?? kTtsRateDefault);
      final migrated = migrateTtsModeAndTier(
        p.getString(kTtsModePrefsKey),
        tier: p.getInt('asr_tts_skill_tier_v1'),
      );
      mode = migrated.mode;
      skillTier = migrated.tier;
      if (p.getString(kTtsModePrefsKey) != mode) {
        await p.setString(kTtsModePrefsKey, mode);
      }
      await p.setInt('asr_tts_skill_tier_v1', skillTier);
      voice = normalizeTtsVoice(p.getString(kTtsVoicePrefsKey));
      error = null;
    } catch (e) {
      rate = kTtsRateDefault;
      mode = kTtsModeFixed;
      voice = kTtsDefaultVoice;
      error = e.toString();
    } finally {
      ready = true;
      notifyListeners();
    }
    // Best-effort voice catalog for Settings + random locale pools.
    await ensureVoicesLoaded(stage: 'bootstrap');
  }

  /// design/219 — after login, re-fetch so sticky 401 from cold start clears.
  Future<void> retryVoicesAfterAuth() async {
    if (hasStickyAuthError) {
      asrEvidenceBus?.record(
        'tts_auth_sticky',
        severity: 'consistency',
        stage: 'pre_login_retry',
        route: 'tts/voices',
        ok: false,
        code: 'auth_required',
        httpStatus: 401,
        details: {
          'has_token': await _hasSessionTokenFlag(),
          'sticky': 1,
          'voice_n': voices.length,
        },
      );
      _authStickyEmitted = true;
    }
    await ensureVoicesLoaded(force: true, stage: 'login_retry');
  }

  Future<void> ensureVoicesLoaded({
    bool force = false,
    String stage = 'force',
  }) async {
    if (!force && voices.isNotEmpty) return;
    final st = stage.trim().isEmpty ? 'force' : stage.trim();
    final hasToken = await _hasSessionTokenFlag();
    asrEvidenceBus?.record(
      'tts_voices_call_start',
      severity: 'lifecycle',
      stage: st,
      route: 'tts/voices',
      ok: true,
      details: {
        'has_token': hasToken,
        'force': force ? 1 : 0,
        'voice_n': voices.length,
      },
    );
    voicesLoading = true;
    notifyListeners();
    var httpStatus = 0;
    var code = 'ok';
    try {
      final info = await _client.fetchTtsVoices();
      if (info.voices.isNotEmpty) {
        voices = List<TtsVoiceChoice>.unmodifiable(info.voices);
      }
      if (voice.isEmpty || voice == 'undefined') {
        voice = normalizeTtsVoice(info.defaultVoice);
      }
      // Keep selected voice if still in catalog; else fall back to default.
      final ids = voices.map((v) => v.id).toSet();
      if (ids.isNotEmpty && !ids.contains(voice)) {
        voice = normalizeTtsVoice(info.defaultVoice);
      }
      error = null;
      _authStickyEmitted = false;
      httpStatus = 200;
      code = 'ok';
    } on AsrApiException catch (e) {
      // EDGE: offline / 503 — keep last list or empty; fixed mode still works.
      error = e.toString();
      httpStatus = e.statusCode ?? 0;
      code = e.statusCode == 401 ? 'auth_required' : 'other';
    } catch (e) {
      error = e.toString();
      httpStatus = 0;
      code = 'other';
    } finally {
      final sticky = hasStickyAuthError ? 1 : 0;
      asrEvidenceBus?.record(
        'tts_voices_call_done',
        severity: code == 'ok' ? 'boundary' : 'error',
        stage: st,
        route: 'tts/voices',
        ok: code == 'ok',
        code: code,
        httpStatus: httpStatus > 0 ? httpStatus : null,
        message: (error ?? '').length > 200
            ? (error ?? '').substring(0, 200)
            : (error ?? ''),
        details: {
          'has_token': hasToken,
          'sticky': sticky,
          'voice_n': voices.length,
        },
      );
      // design/219 — separate consistency kind so agents can pull without
      // filtering every voices done; once per sticky episode.
      if (sticky == 1 && !_authStickyEmitted) {
        _authStickyEmitted = true;
        asrEvidenceBus?.record(
          'tts_auth_sticky',
          severity: 'consistency',
          stage: st,
          route: 'tts/voices',
          ok: false,
          code: code,
          httpStatus: httpStatus > 0 ? httpStatus : null,
          details: {
            'has_token': hasToken,
            'sticky': 1,
            'voice_n': voices.length,
          },
        );
      }
      voicesLoading = false;
      notifyListeners();
    }
  }

  void _onLibraryChanged() {
    final s = _library.session;
    final sid = s?.sessionId;
    final idx = s?.sentenceIndex;
    // Stop when paper closes or sentence index changes (PC parity: move → stop).
    if (sid != _lastSessionId || idx != _lastSentenceIndex) {
      _lastSessionId = sid;
      _lastSentenceIndex = idx;
      if (playing || loading) {
        stop();
      }
    }
  }

  Future<void> setRate(double value) async {
    rate = clampSpeakingRate(value);
    try {
      await _player.setPlaybackRate(rate);
    } catch (_) {
      // EDGE: player not ready
    }
    try {
      final p = await _readyPrefs();
      await p.setDouble(kTtsRatePrefsKey, rate);
      error = null;
    } catch (e) {
      error = e.toString();
    }
    notifyListeners();
  }

  Future<void> setMode(String value) async {
    mode = normalizeTtsMode(value);
    try {
      final p = await _readyPrefs();
      await p.setString(kTtsModePrefsKey, mode);
      error = null;
    } catch (e) {
      error = e.toString();
    }
    notifyListeners();
  }

  Future<void> setVoice(String value) async {
    voice = normalizeTtsVoice(value);
    try {
      final p = await _readyPrefs();
      await p.setString(kTtsVoicePrefsKey, voice);
      error = null;
    } catch (e) {
      error = e.toString();
    }
    notifyListeners();
  }

  /// Current play params (fixed settings or one random draw).
  TtsPlaybackParams pickPlaybackParams() {
    return pickTtsPlaybackParams(
      mode: mode,
      voice: voice,
      speakingRate: rate,
      voiceIds: voices.map((v) => v.id).toList(growable: false),
      random: _random,
      skillTier: skillTier,
    );
  }

  void setSkillTier(int tier) {
    final t = tier.clamp(0, 5);
    if (skillTier == t) return;
    skillTier = t;
    () async {
      try {
        final p = await _readyPrefs();
        await p.setInt('asr_tts_skill_tier_v1', skillTier);
      } catch (_) {}
    }();
    notifyListeners();
  }

  /// Fetch + play English text of the current sentence.
  Future<void> playCurrentSentence() async {
    final s = _library.session;
    final cur = s?.currentSentence;
    final text = cur?.text ?? '';
    await playText(text);
  }

  /// Fetch + play arbitrary English text with current mode/voice/rate.
  Future<void> playText(String text) async {
    text = cite.stripCiteMarkersForDisplay(text);
    if (isEmptyTtsText(text)) {
      error = 'No sentence text to speak.';
      playing = false;
      loading = false;
      notifyListeners();
      return;
    }
    loading = true;
    error = null;
    notifyListeners();
    try {
      await _player.stop();
      final params = pickPlaybackParams();
      final Uint8List bytes = await _client.synthesizeTts(
        text: text,
        voice: params.voice,
        // Server ignores rate for cache; always request native 1.0.
        speakingRate: kTtsRateDefault,
      );
      if (bytes.isEmpty) {
        throw AsrApiException('empty audio body', 502);
      }
      await _player.setPlaybackRate(clampSpeakingRate(params.speakingRate));
      await _player.play(BytesSource(bytes, mimeType: 'audio/mpeg'));
      playing = true;
    } on AsrApiException catch (e) {
      error = e.message;
      playing = false;
      // design/219 — synthesize path must leave a joinable auth fail (not only UI).
      asrEvidenceBus?.record(
        'client_api_fail',
        severity: 'error',
        stage: 'play',
        route: 'tts',
        ok: false,
        code: e.statusCode == 401 ? 'auth_required' : 'other',
        httpStatus: e.statusCode,
        message: e.message.length > 200 ? e.message.substring(0, 200) : e.message,
        details: {
          'has_token': await _hasSessionTokenFlag(),
          'voice_n': voices.length,
        },
      );
    } catch (e) {
      error = e.toString();
      playing = false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> stop() async {
    try {
      await _player.stop();
    } catch (_) {
      // EDGE: already disposed / never started
    }
    playing = false;
    loading = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _library.removeListener(_onLibraryChanged);
    _player.dispose();
    super.dispose();
  }
}
