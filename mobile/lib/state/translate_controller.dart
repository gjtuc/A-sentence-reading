/// Translate opt-in controller (design/99).
///
/// Live Enable / IPS stay out of ASR.
library;

import 'package:flutter/foundation.dart';

import '../api/translate_models.dart';
import '../api/translate_store.dart';

class TranslateController extends ChangeNotifier {
  TranslateController({TranslateStore? store})
      : _store = store ?? PrefsTranslateStore();

  final TranslateStore _store;

  /// User preference (device, scoped by uid). Default false.
  bool enabled = false;

  bool ready = false;
  String? error;
  String? _uid;

  /// Load prefs for [uid]. Call on login / account switch.
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    try {
      final raw = await _store.readRaw(_uid);
      enabled = parseTranslateEnabledPref(raw);
      error = null;
    } catch (e) {
      // EDGE: prefs failure → stay OFF (fail-closed).
      enabled = false;
      error = e.toString();
    } finally {
      ready = true;
    }
    notifyListeners();
  }

  /// Logout / logged-out shell: clear in-memory ON so next account starts clean.
  void clearSession() {
    _uid = null;
    enabled = false;
    error = null;
    notifyListeners();
  }

  Future<void> setEnabled(bool next) async {
    enabled = next;
    notifyListeners();
    try {
      await _store.writeRaw(_uid, serializeTranslateEnabledPref(next));
      error = null;
    } catch (e) {
      error = e.toString();
      notifyListeners();
    }
  }
}
