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

  /// Curated list from GET /api/tts/voices (may be empty until loaded).
  List<TtsVoiceChoice> voices = const [];

  bool get isRandomMode => isTtsRandomMode(mode);

  int? _lastSentenceIndex;
  String? _lastSessionId;

  Future<SharedPreferences> _readyPrefs() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  /// Load persisted mode / voice / rate once at cold start.
  Future<void> bootstrap() async {
    try {
      final p = await _readyPrefs();
      final rawRate = p.getDouble(kTtsRatePrefsKey);
      rate = clampSpeakingRate(rawRate ?? kTtsRateDefault);
      mode = normalizeTtsMode(p.getString(kTtsModePrefsKey));
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
    await ensureVoicesLoaded();
  }

  Future<void> ensureVoicesLoaded({bool force = false}) async {
    if (!force && voices.isNotEmpty) return;
    voicesLoading = true;
    notifyListeners();
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
    } catch (e) {
      // EDGE: offline / 503 — keep last list or empty; fixed mode still works.
      error = e.toString();
    } finally {
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
    );
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
