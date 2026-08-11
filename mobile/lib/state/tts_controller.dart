/// Plays current sentence via Cloud TTS (design/64).
///
/// Server synthesizes + GCS-caches MP3; this controller only fetches bytes
/// and feeds audioplayers. Live Enable / IPS stay out of ASR.
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import '../api/tts_models.dart';
import 'library_controller.dart';

const String kTtsRatePrefsKey = 'asr_tts_rate_v1';

class TtsController extends ChangeNotifier {
  TtsController({
    required AsrClient client,
    required LibraryController library,
    AudioPlayer? player,
    SharedPreferences? prefs,
  })  : _client = client,
        _library = library,
        _player = player ?? AudioPlayer(),
        _prefs = prefs {
    _library.addListener(_onLibraryChanged);
    _player.onPlayerComplete.listen((_) {
      playing = false;
      notifyListeners();
    });
  }

  final AsrClient _client;
  final LibraryController _library;
  final AudioPlayer _player;
  SharedPreferences? _prefs;

  bool loading = false;
  bool playing = false;
  bool ready = false;
  String? error;

  /// Client-side speed only (server caches native 1.0).
  double rate = kTtsRateDefault;

  /// Optional voice override; null → server default.
  String? voice;

  int? _lastSentenceIndex;
  String? _lastSessionId;

  Future<SharedPreferences> _readyPrefs() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  /// Load persisted playback rate once at cold start (design/96).
  Future<void> bootstrap() async {
    try {
      final p = await _readyPrefs();
      final raw = p.getDouble(kTtsRatePrefsKey);
      rate = clampSpeakingRate(raw ?? kTtsRateDefault);
      error = null;
    } catch (e) {
      rate = kTtsRateDefault;
      error = e.toString();
    } finally {
      ready = true;
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

  /// Fetch + play English text of the current sentence.
  Future<void> playCurrentSentence() async {
    final s = _library.session;
    final cur = s?.currentSentence;
    final text = cur?.text ?? '';
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
      final Uint8List bytes = await _client.synthesizeTts(
        text: text,
        voice: voice,
        // Server ignores rate for cache; always request native 1.0.
        speakingRate: kTtsRateDefault,
      );
      if (bytes.isEmpty) {
        throw AsrApiException('empty audio body', 502);
      }
      await _player.setPlaybackRate(clampSpeakingRate(rate));
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
