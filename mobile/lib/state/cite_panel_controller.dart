/// Cite References panel opt-in controller (design/148).
library;

import 'package:flutter/foundation.dart';

import '../api/cite_panel_models.dart';
import '../api/cite_panel_store.dart';

class CitePanelController extends ChangeNotifier {
  CitePanelController({CitePanelStore? store})
      : _store = store ?? PrefsCitePanelStore();

  final CitePanelStore _store;

  /// User preference (device, scoped by uid). Default true.
  bool enabled = true;

  /// Server kill from `/api/status` — false → hide panel + disable settings toggle.
  bool serverAvailable = true;

  bool ready = false;
  String? error;
  String? _uid;

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    try {
      final raw = await _store.readRaw(_uid);
      enabled = parseCitePanelEnabledPref(raw);
      error = null;
    } catch (e) {
      // EDGE: prefs failure → stay ON (fail-open).
      enabled = true;
      error = e.toString();
    } finally {
      ready = true;
      notifyListeners();
    }
  }

  void clearSession() {
    _uid = null;
    enabled = true;
    error = null;
    notifyListeners();
  }

  void setServerAvailable(bool next) {
    if (serverAvailable == next) return;
    serverAvailable = next;
    notifyListeners();
  }

  Future<void> setEnabled(bool next) async {
    enabled = next;
    notifyListeners();
    try {
      await _store.writeRaw(_uid, serializeCitePanelEnabledPref(next));
      error = null;
    } catch (e) {
      error = e.toString();
      notifyListeners();
    }
  }
}
