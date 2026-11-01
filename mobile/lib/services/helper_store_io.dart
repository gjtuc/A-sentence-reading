/// design/495 — the phone side: it never keeps copies in the helper, it only
/// checks over the cable that the helper is running.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'helper_store.dart';

Future<(HelperLine, Map<String, Object?>)?> connectHelperStore({
  bool ask = false,
}) async =>
    null;

void markHelperWanted() {}

Future<HelperWatch?> connectHelperWatch() async => null;

Future<void> askBrowserToKeepStorage() async {}

/// The helper's hello through `adb reverse` of [kHelperProbePort], or null.
Future<Map<String, Object?>?> probeHelperFromPhone({
  Duration limit = kHelperOpenLimit,
}) async {
  Socket? s;
  try {
    s = await Socket.connect('127.0.0.1', kHelperProbePort, timeout: limit);
    final line = await s
        .cast<List<int>>()
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .first
        .timeout(limit);
    final m = jsonDecode(line);
    if (m is Map && m['t'] == 'hello') return Map<String, Object?>.from(m);
  } catch (_) {
  } finally {
    s?.destroy();
  }
  return null;
}

/// design/504 — `flutter test` on the PC would reach the real helper through
/// 127.0.0.1 and pass for a phone on the cable.
bool get cableAutoSyncHere => !Platform.environment.containsKey('FLUTTER_TEST');

Future<bool> runInOneWindow(String name, Future<void> Function() body) async {
  await body();
  return true;
}
