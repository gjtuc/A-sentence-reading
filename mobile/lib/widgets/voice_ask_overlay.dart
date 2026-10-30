/// design/475 — speaking an AI question. The whole screen listens: its edges
/// glow with the voice, a tap anywhere ends the question, and only then is the
/// recording written down. There is no silence cut-off, so a pause to think
/// does not end the question.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import '../api/voice_ask_models.dart';
import '../services/evidence_bus.dart';
import '../services/shadow_mic.dart';

typedef VoiceAskTranscribe = Future<VoiceAskHeard> Function(
  MicTake take,
  String sentence,
);

/// What the question box needs to offer the microphone.
class VoiceAskSource {
  const VoiceAskSource({
    required this.sentence,
    required this.transcribe,
    this.newMic = ShadowMic.new,
    this.listeningText = kVoiceAskListening,
    this.tapToEndText = kVoiceAskTapToEnd,
    this.hintText = kVoiceAskMixHint,
  });

  /// The English sentence on screen; the server spells its words from it.
  final String sentence;
  final VoiceAskTranscribe transcribe;
  final ShadowMic Function() newMic;

  /// design/490 — the same screen dictates a library title.
  final String listeningText;
  final String tapToEndText;
  final String hintText;
}

const String kVoiceAskListening = '음성으로 질문하는 중이에요.';
const String kVoiceAskTapToEnd = '아무 곳이나 누르면 질문이 끝나요.';
const String kVoiceAskMixHint = '한국어와 영어를 섞어 말해도 돼요.';
const String kVoiceAskWriting = '글자로 바꾸는 중이에요…';

/// The written question, or null when cancelled or nothing came of it.
Future<String?> showVoiceAskOverlay(
  BuildContext context, {
  required VoiceAskSource source,
}) {
  return showGeneralDialog<String>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    barrierColor: Colors.black.withValues(alpha: 0.62),
    transitionDuration: const Duration(milliseconds: 180),
    pageBuilder: (ctx, _, __) => VoiceAskOverlay(source: source),
  );
}

enum _Phase { opening, listening, writing, failed }

class VoiceAskOverlay extends StatefulWidget {
  const VoiceAskOverlay({super.key, required this.source});

  final VoiceAskSource source;

  @override
  State<VoiceAskOverlay> createState() => _VoiceAskOverlayState();
}

class _VoiceAskOverlayState extends State<VoiceAskOverlay>
    with SingleTickerProviderStateMixin {
  late final ShadowMic _mic = widget.source.newMic();

  /// A ticker, not an AnimationController: the glow keeps moving where the
  /// platform asks for fewer animations (design/475).
  late final Ticker _ticker = createTicker(_onTick);
  final ValueNotifier<({double level, double turn})> _frame =
      ValueNotifier((level: 0, turn: 0));
  final ValueNotifier<Duration> _clock = ValueNotifier(Duration.zero);
  final FocusNode _focus = FocusNode(debugLabel: 'voice_ask');
  Timer? _meter;
  bool _metering = false;
  double _heard = 0;
  Duration _startedAt = Duration.zero;
  Duration _now = Duration.zero;
  _Phase _phase = _Phase.opening;
  String _message = '';
  bool _recording = false;
  bool _closed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_start());
  }

  void _record(String code, {bool? ok, Map<String, Object?> details = const {}}) {
    asrEvidenceBus?.record(
      'voice_ask_client',
      ok: ok,
      code: code,
      details: {'secs': _clock.value.inSeconds, ...details},
    );
  }

  Future<void> _start() async {
    setState(() {
      _phase = _Phase.opening;
      _message = '';
    });
    _clock.value = Duration.zero;
    if (!await _mic.ensurePermission()) {
      _record('mic_denied', ok: false);
      return _fail('마이크를 쓸 수 있게 허용한 뒤 다시 눌러 주세요.');
    }
    if (!mounted || _closed) return;
    if (!await _mic.start('voice_ask', usePrimed: false)) {
      _record('mic_failed', ok: false);
      return _fail('마이크를 열지 못했어요.');
    }
    if (!mounted || _closed) {
      unawaited(_mic.cancel());
      return;
    }
    _recording = true;
    _heard = 0;
    _startedAt = _now;
    if (!_ticker.isActive) unawaited(_ticker.start());
    _meter = Timer.periodic(const Duration(milliseconds: 70), (_) => _readLevel());
    setState(() => _phase = _Phase.listening);
  }

  Future<void> _readLevel() async {
    if (_metering || !_recording) return;
    _metering = true;
    try {
      _heard = await _mic.level();
    } finally {
      _metering = false;
    }
  }

  void _onTick(Duration elapsed) {
    _now = elapsed;
    _frame.value = (
      level: voiceGlowStep(_frame.value.level, _recording ? _heard : 0),
      turn: elapsed.inMicroseconds / 1e6 / 14,
    );
    if (!_recording) return;
    final took = elapsed - _startedAt;
    _clock.value = took;
    if (took >= kVoiceAskMax) unawaited(_finish());
  }

  void _stopListening() {
    _recording = false;
    _meter?.cancel();
    _meter = null;
  }

  void _fail(String message) {
    _stopListening();
    if (!mounted || _closed) return;
    setState(() {
      _phase = _Phase.failed;
      _message = message;
    });
  }

  Future<void> _finish() async {
    if (_phase != _Phase.listening) return;
    _stopListening();
    setState(() => _phase = _Phase.writing);
    final take = await _mic.stop();
    if (!mounted || _closed) return;
    if (take == null || take.bytes.isEmpty) {
      _record('empty_take', ok: false);
      return _fail('녹음된 소리가 없어요. 다시 해 볼까요?');
    }
    final heard = await widget.source.transcribe(take, widget.source.sentence);
    if (!mounted || _closed) return;
    if (!heard.ok) {
      _record('transcribe_failed', ok: false, details: {'error': heard.error});
      return _fail(voiceAskErrorKo(heard.error));
    }
    final text = heard.text.trim();
    if (text.isEmpty) {
      _record('nothing_heard', ok: false, details: {'bytes': take.bytes.length});
      return _fail('알아들은 말이 없어요. 다시 해 볼까요?');
    }
    _record('heard', ok: true, details: {'chars': text.length, 'bytes': take.bytes.length});
    _close(text);
  }

  void _cancel() {
    if (_phase == _Phase.listening || _phase == _Phase.writing) {
      _record('cancel', details: {'phase': _phase.name});
    }
    _close(null);
  }

  void _close(String? text) {
    if (_closed) return;
    _closed = true;
    _stopListening();
    Navigator.of(context).pop(text);
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.escape) {
      _cancel();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.enter ||
        key == LogicalKeyboardKey.numpadEnter ||
        key == LogicalKeyboardKey.space) {
      if (_phase == _Phase.listening) unawaited(_finish());
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  void _onTap() {
    switch (_phase) {
      case _Phase.listening:
        unawaited(_finish());
      case _Phase.failed:
        _cancel();
      case _Phase.opening:
      case _Phase.writing:
        break;
    }
  }

  @override
  void dispose() {
    _stopListening();
    _ticker.dispose();
    _mic.dispose();
    _frame.dispose();
    _clock.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const ink = Colors.white;
    final body = theme.textTheme.titleMedium?.copyWith(color: ink, height: 1.5);
    final small = theme.textTheme.bodyMedium?.copyWith(color: ink.withValues(alpha: 0.75));
    return PopScope(
      onPopInvokedWithResult: (didPop, _) {
        if (didPop && !_closed) {
          _closed = true;
          if (_phase == _Phase.listening || _phase == _Phase.writing) {
            _record('cancel', details: {'phase': _phase.name, 'via': 'back'});
          }
        }
      },
      child: Focus(
        focusNode: _focus,
        autofocus: true,
        onKeyEvent: _onKey,
        child: Material(
          type: MaterialType.transparency,
          child: GestureDetector(
            key: const ValueKey('voice_ask_surface'),
            behavior: HitTestBehavior.opaque,
            onTap: _onTap,
            child: Stack(
              fit: StackFit.expand,
              children: [
                IgnorePointer(
                  child: RepaintBoundary(
                    child: ValueListenableBuilder(
                      valueListenable: _frame,
                      builder: (context, f, _) => CustomPaint(
                        painter: VoiceEdgeGlowPainter(level: f.level, turn: f.turn),
                      ),
                    ),
                  ),
                ),
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                    child: Column(
                      children: [
                        const Spacer(),
                        _centre(body, small),
                        const Spacer(),
                        TextButton(
                          key: const ValueKey('voice_ask_cancel'),
                          onPressed: _cancel,
                          style: TextButton.styleFrom(foregroundColor: ink.withValues(alpha: 0.8)),
                          child: const Text('취소'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _centre(TextStyle? body, TextStyle? small) {
    switch (_phase) {
      case _Phase.opening:
        return const SizedBox(
          width: 28,
          height: 28,
          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
        );
      case _Phase.listening:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ValueListenableBuilder(
              valueListenable: _frame,
              builder: (context, f, child) =>
                  Transform.scale(scale: 1 + f.level * 0.18, child: child),
              child: const Icon(Icons.mic, size: 56, color: Colors.white),
            ),
            const SizedBox(height: 20),
            Text(
              '${widget.source.listeningText}\n${widget.source.tapToEndText}',
              textAlign: TextAlign.center,
              style: body,
            ),
            const SizedBox(height: 12),
            ValueListenableBuilder<Duration>(
              valueListenable: _clock,
              builder: (context, d, _) => Text(voiceAskClock(d), style: small),
            ),
            const SizedBox(height: 8),
            Text(widget.source.hintText, style: small, textAlign: TextAlign.center),
          ],
        );
      case _Phase.writing:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            ),
            const SizedBox(height: 16),
            Text(kVoiceAskWriting, style: body),
          ],
        );
      case _Phase.failed:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_message, textAlign: TextAlign.center, style: body),
            const SizedBox(height: 16),
            FilledButton.tonal(
              key: const ValueKey('voice_ask_retry'),
              onPressed: () => unawaited(_start()),
              child: const Text('다시 말하기'),
            ),
          ],
        );
    }
  }
}

/// A soft band of colour along the screen edges. It widens and brightens with
/// the voice and turns slowly, so it reads as listening, not as flashing.
class VoiceEdgeGlowPainter extends CustomPainter {
  VoiceEdgeGlowPainter({required this.level, required this.turn});

  final double level;

  /// Full turns of the colour ring so far.
  final double turn;

  static const List<Color> colors = [
    Color(0xFF5B8CFF),
    Color(0xFFA66BFF),
    Color(0xFFFF6FB1),
    Color(0xFFFFA65C),
    Color(0xFF4FD1C5),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final v = level.clamp(0.0, 1.0);
    final rect = Offset.zero & size;
    final shader = SweepGradient(
      colors: [...colors, colors.first],
      transform: GradientRotation(turn * 2 * math.pi),
    ).createShader(rect);
    final radius = Radius.circular(math.min(36, size.shortestSide / 8));
    final edge = RRect.fromRectAndRadius(rect, radius);
    final soft = 18 + 46 * v;
    canvas.drawRRect(
      edge,
      Paint()
        ..shader = shader
        ..style = PaintingStyle.stroke
        ..strokeWidth = soft * 2
        ..color = Color.fromRGBO(0, 0, 0, 0.35 + 0.5 * v)
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, soft * 0.6),
    );
    canvas.drawRRect(
      edge.deflate(1.5),
      Paint()
        ..shader = shader
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3 + 5 * v
        ..color = Color.fromRGBO(0, 0, 0, 0.55 + 0.45 * v)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2),
    );
  }

  @override
  bool shouldRepaint(VoiceEdgeGlowPainter old) =>
      old.level != level || old.turn != turn;
}
