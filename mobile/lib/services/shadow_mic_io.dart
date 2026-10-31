import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'shadow_mic.dart';

ShadowMic createShadowMic() => _ChannelMic();

class _ChannelMic implements ShadowMic {
  // WHY: design/82 — Android MediaRecorder via platform channel (no pub `record` dep).
  static const _ch = MethodChannel('asr/shadowing_mic');

  String? _primed;

  /// A refusal is the only trouble the phone reports, through [ensurePermission].
  @override
  MicTrouble get trouble => MicTrouble.none;
  String? _path;

  Future<String> _newPath(String tag) async {
    final dir = await getTemporaryDirectory();
    return '${dir.path}${Platform.pathSeparator}asr_${tag}_${DateTime.now().millisecondsSinceEpoch}.m4a';
  }

  @override
  Future<bool> ensurePermission() async {
    var ok = await _ch.invokeMethod<bool>('hasPermission') ?? false;
    if (!ok) ok = await _ch.invokeMethod<bool>('requestPermission') ?? false;
    return ok;
  }

  @override
  Future<bool> prepare(String tag) async {
    _primed = null;
    final path = await _newPath(tag);
    final ok = await _ch.invokeMethod<bool>('prepare', {'path': path}) ?? false;
    _primed = ok ? path : null;
    return ok;
  }

  @override
  Future<bool> start(String tag, {bool usePrimed = true}) async {
    final primed = usePrimed ? _primed : null;
    if (usePrimed) _primed = null;
    final path = primed ?? await _newPath(tag);
    final ok = await _ch.invokeMethod<bool>('start', {'path': path}) ?? false;
    _path = ok ? path : null;
    return ok;
  }

  @override
  Future<MicTake?> stop() async {
    final out = await _ch.invokeMethod<String>('stop');
    final path = (out == null || out.isEmpty) ? _path : out;
    _path = null;
    if (path == null) return null;
    final file = File(path);
    if (!await file.exists()) return null;
    return MicTake(bytes: await file.readAsBytes(), mime: 'audio/mp4', path: path);
  }

  @override
  Future<void> cancel() async {
    _primed = null;
    _path = null;
    try {
      await _ch.invokeMethod<String>('stop');
    } catch (_) {}
  }

  @override
  Future<double> level() async {
    try {
      return micLevelFromAmplitude(await _ch.invokeMethod<int>('level') ?? 0);
    } catch (_) {
      return 0;
    }
  }

  @override
  void dispose() => unawaited(cancel());
}
