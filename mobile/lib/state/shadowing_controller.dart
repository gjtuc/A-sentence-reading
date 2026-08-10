/// Shadowing practice opt-in controller (design/79).
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

  /// Load prefs for [uid]. Call on login / account switch.
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    try {
      final raw = await _store.readRaw(_uid);
      enabled = parseShadowingEnabledPref(raw);
      error = null;
    } catch (e) {
      // EDGE: prefs failure → stay OFF (fail-closed).
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
    enabled = false;
    error = null;
    notifyListeners();
  }

  void setServerAvailable(bool on) {
    if (serverAvailable == on) return;
    serverAvailable = on;
    notifyListeners();
  }

  Future<void> setEnabled(bool next) async {
    // WHY: ignore client tap when server kill is off — no false success.
    if (!serverAvailable) {
      error = '서버에서 쉐도잉 연습이 꺼져 있습니다.';
      notifyListeners();
      return;
    }
    enabled = next;
    notifyListeners();
    try {
      await _store.writeRaw(_uid, serializeShadowingEnabledPref(next));
      error = null;
    } catch (e) {
      error = e.toString();
      notifyListeners();
    }
  }
}
