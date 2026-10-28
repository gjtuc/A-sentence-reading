import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/practice_pause.dart';
import 'package:sentence_reading/services/shadow_mic.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  late List<MethodCall> calls;
  var allowed = true;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('shadow_mic_');
    calls = [];
    allowed = true;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => dir.path,
    );
    String? recording;
    messenger.setMockMethodCallHandler(
      const MethodChannel('asr/shadowing_mic'),
      (call) async {
        calls.add(call);
        switch (call.method) {
          case 'hasPermission':
            return allowed;
          case 'requestPermission':
            return false;
          case 'prepare':
            return true;
          case 'start':
            recording = (call.arguments as Map)['path'] as String;
            return true;
          case 'stop':
            final path = recording;
            recording = null;
            if (path != null) File(path).writeAsBytesSync([1, 2, 3]);
            return path;
        }
        return null;
      },
    );
  });

  tearDown(() => dir.deleteSync(recursive: true));

  String pathOf(String method) => (calls
          .lastWhere((c) => c.method == method)
          .arguments as Map)['path'] as String;

  test('the phone records into an M4A file and hands back its bytes', () async {
    final mic = ShadowMic();
    expect(await mic.ensurePermission(), isTrue);
    expect(await mic.prepare('shadow'), isTrue);
    expect(await mic.start('shadow'), isTrue);
    expect(pathOf('start'), pathOf('prepare'), reason: 'the prepared take is used');
    final take = await mic.stop();
    expect(take, isNotNull);
    expect(take!.bytes, [1, 2, 3]);
    expect(take.mime, 'audio/mp4');
    expect(take.path, endsWith('.m4a'));
    expect(take.durationMs, -1, reason: 'the file is probed for its length');
  });

  test('a review take leaves the prepared speak take alone', () async {
    final mic = ShadowMic();
    await mic.prepare('shadow');
    final primed = pathOf('prepare');
    await mic.start('review', usePrimed: false);
    expect(pathOf('start'), isNot(primed));
    await mic.stop();
    await mic.start('shadow');
    expect(pathOf('start'), primed);
  });

  test('no permission, and a stop with nothing recorded', () async {
    allowed = false;
    final mic = ShadowMic();
    expect(await mic.ensurePermission(), isFalse);
    expect(calls.map((c) => c.method), ['hasPermission', 'requestPermission']);
    expect(await mic.stop(), isNull);
  });

  test('a browser window losing focus does not stop practice; a hidden tab does', () {
    expect(practicePausesOn(AppLifecycleState.inactive, web: true), isFalse);
    expect(practicePausesOn(AppLifecycleState.hidden, web: true), isTrue);
    expect(practicePausesOn(AppLifecycleState.paused, web: true), isTrue);
    expect(practicePausesOn(AppLifecycleState.inactive, web: false), isTrue);
    expect(practicePausesOn(AppLifecycleState.paused, web: false), isTrue);
    expect(practicePausesOn(AppLifecycleState.resumed, web: false), isFalse);
  });

  test('design/475 the phone reads the recorder peak as a level', () async {
    final mic = ShadowMic();
    expect(await mic.level(), 0, reason: 'an old app without the call reads silence');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('asr/shadowing_mic'),
      (call) async => call.method == 'level' ? 32767 : null,
    );
    expect(await mic.level(), 1);
  });
}
