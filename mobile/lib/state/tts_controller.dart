/// Plays current sentence via Cloud TTS (design/64).
///
/// Server synthesizes + GCS-caches MP3; this controller only fetches bytes
/// and feeds audioplayers. Live Enable / IPS stay out of ASR.
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/tts_models.dart';
import 'library_controller.dart';

class TtsController extends ChangeNotifier {
  TtsController({
    required AsrClient client,
    required LibraryController library,
    AudioPlayer? player,
  })  : _client = client,
        _library = library,
        _player = player ?? AudioPlayer() {
    _library.addListener(_onLibraryChanged);
    _player.onPlayerComplete.listen((_) {
      playing = false;
      notifyListeners();
    });
  }

  final AsrClient _client;
  final LibraryController _library;
  final AudioPlayer _player;

  bool loading = false;
  bool playing = false;
  String? error;

  /// Client-side speed only (server caches native 1.0).
  double rate = kTtsRateDefault;

  /// Optional voice override; null → server default.
  String? voice;

  int? _lastSentenceIndex;
  String? _lastSessionId;

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
