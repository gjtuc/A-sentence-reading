/// Shadowing practice opt-in controller (design/79 · design/160 auto-off).
///
/// Live Enable / IPS stay out of ASR.
library;

import 'package:flutter/foundation.dart';

import '../api/shadowing_models.dart';
import '../api/shadowing_store.dart';

class ShadowingController extends ChangeNotifier {
  ShadowingController({ShadowingStore? store})
      : _store = store ?? PrefsShadowingStore();

  final ShadowingStore _store;

  /// User preference (device, scoped by uid). Default false.
  bool enabled = false;

  /// Server kill from `/api/status` — false → UI must not pretend kill is on.
  bool serverAvailable = false;

  bool ready = false;
  String? error;
  String? _uid;
  ShadowingPrefs _prefs = const ShadowingPrefs();

  /// Load prefs for [uid]. Call on login / account switch.
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    try {
      final raw = await _store.readRaw(_uid);
      _prefs = parseShadowingPrefs(raw);
      enabled = _prefs.enabled;
      error = null;
      await _applyAutoOffIfStale(notify: false);
    } catch (e) {
      // EDGE: prefs failure → stay OFF (fail-closed).
      _prefs = const ShadowingPrefs();
      enabled = false;
      error = e.toString();
    } finally {
      ready = true;
      notifyListeners();
    }
  }

  /// Logout / logged-out shell: clear in-memory ON so next account starts clean.
  void clearSession() {
    _uid = null;
    _prefs = const ShadowingPrefs();
    enabled = false;
    error = null;
    notifyListeners();
  }

  void setServerAvailable(bool on) {
    if (serverAvailable == on) return;
    serverAvailable = on;
    notifyListeners();
  }

  /// design/160 — check 90d idle before settings / resume / reader entry.
  Future<void> applyAutoOffIfStale() => _applyAutoOffIfStale();

  Future<void> _applyAutoOffIfStale({bool notify = true}) async {
    if (!shouldAutoOffShadowing(_prefs)) return;
    _prefs = _prefs.copyWith(enabled: false);
    enabled = false;
    try {
      await _store.writeRaw(_uid, serializeShadowingPrefs(_prefs));
      error = null;
    } catch (e) {
      error = e.toString();
    }
    if (notify) notifyListeners();
  }

  /// design/160 — user pressed reading 「연습」.
  Future<void> recordPracticePressed() async {
    final now = DateTime.now().toUtc().toIso8601String();
    _prefs = _prefs.copyWith(lastPracticePressedAt: now);
    try {
      await _store.writeRaw(_uid, serializeShadowingPrefs(_prefs));
      error = null;
    } catch (e) {
      error = e.toString();
      notifyListeners();
    }
  }

  Future<void> setEnabled(bool next) async {
    // WHY: prefs always writable — server kill gates practice APIs, not the toggle.
    final now = DateTime.now().toUtc().toIso8601String();
    _prefs = _prefs.copyWith(
      enabled: next,
      enabledSince: next ? now : _prefs.enabledSince,
    );
    enabled = next;
    notifyListeners();
    try {
      await _store.writeRaw(_uid, serializeShadowingPrefs(_prefs));
      error = null;
    } catch (e) {
      error = e.toString();
      notifyListeners();
    }
  }
}
