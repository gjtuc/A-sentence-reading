/// design/250 — login/resume pull + debounced push for focus/skill prefs.
library;

import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'client.dart';
import 'focus_practice_models.dart';
import 'focus_practice_store.dart';
import 'practice_cloud_merge.dart';
import 'practice_cloud_hooks.dart';
import '../practice_skill/skill_adapt.dart';
import '../practice_skill/skill_store.dart';
import '../services/evidence_bus.dart';

class PracticeCloudSync {
  AsrClient? _client;
  bool serverAvailable = false;
  String? _uid;
  bool _pulledSession = false;
  Timer? _focusPushTimer;
  Timer? _skillPushTimer;

  void attachClient(AsrClient client) {
    _client = client;
    bindHooks();
  }

  void bindHooks() {
    asrSchedulePushFocus = schedulePushFocus;
    asrSchedulePushSkill = schedulePushSkill;
    asrPracticeEnsurePulled = ensurePulled;
  }

  void setServerAvailable(bool v) {
    serverAvailable = v;
  }

  Future<void> bindUid(String? uid) async {
    final next = (uid ?? '').trim();
    if (next != (_uid ?? '')) {
      _pulledSession = false;
    }
    _uid = next.isEmpty ? null : next;
  }

  void clearSession() {
    _uid = null;
    _pulledSession = false;
    serverAvailable = false;
    _focusPushTimer?.cancel();
    _skillPushTimer?.cancel();
  }

  /// Pull+merge once per login session (login / resume / practice open).
  Future<void> ensurePulled({bool force = false}) async {
    if (_uid == null) return;
    if (_pulledSession && !force) return;
    await pullAll();
    _pulledSession = true;
  }

  Future<void> pullAll() async {
    await Future.wait([pullFocus(), pullSkill()]);
  }

  Future<FocusPracticeHistory?> pullFocus() async {
    final client = _client;
    final uid = _uid;
    if (client == null || uid == null || !serverAvailable) return null;
    final sw = Stopwatch()..start();
    var ok = false;
    try {
      final remote = await client.fetchPracticeFocusSync();
      if (!remote.available || remote.store == null) {
        return null;
      }
      final store = PrefsFocusPracticeStore();
      final localRaw = await store.readRaw(uid);
      final local = parseFocusPracticeHistory(localRaw);
      final remoteH = parseFocusPracticeHistory(jsonEncode(remote.store));
      final merged = mergeFocusHistories(local, remoteH);
      await store.writeRaw(uid, serializeFocusPracticeHistory(merged));
      ok = true;
      return merged;
    } catch (_) {
      return null;
    } finally {
      sw.stop();
      asrEvidenceBus?.record(
        'practice_focus_sync',
        severity: 'lifecycle',
        ok: ok,
        details: {'op': 'pull', 'elapsed_ms': sw.elapsedMilliseconds},
      );
    }
  }

  Future<SkillState?> pullSkill() async {
    final client = _client;
    final uid = _uid;
    if (client == null || uid == null || !serverAvailable) return null;
    final sw = Stopwatch()..start();
    var ok = false;
    try {
      final remote = await client.fetchPracticeSkillSync();
      if (!remote.available || remote.store == null) {
        return null;
      }
      final prefs = await SharedPreferences.getInstance();
      final key = skillPrefsKey(uid);
      final localRaw = prefs.getString(key);
      SkillState local = SkillState(epochTargetN: rollSkillEpochTarget());
      if (localRaw != null && localRaw.isNotEmpty) {
        try {
          final m = jsonDecode(localRaw);
          if (m is Map) {
            local = SkillState.fromJson(Map<String, dynamic>.from(m));
          }
        } catch (_) {}
      }
      final remoteS = SkillState.fromJson(remote.store!);
      final merged = mergeSkillStates(local, remoteS);
      await prefs.setString(key, jsonEncode(merged.toJson()));
      ok = true;
      return merged;
    } catch (_) {
      return null;
    } finally {
      sw.stop();
      asrEvidenceBus?.record(
        'practice_skill_sync',
        severity: 'lifecycle',
        ok: ok,
        details: {'op': 'pull', 'elapsed_ms': sw.elapsedMilliseconds},
      );
    }
  }

  void schedulePushFocus(Map<String, dynamic> store) {
    _focusPushTimer?.cancel();
    _focusPushTimer = Timer(const Duration(milliseconds: 800), () {
      unawaited(pushFocus(store));
    });
  }

  void schedulePushSkill(Map<String, dynamic> store) {
    _skillPushTimer?.cancel();
    _skillPushTimer = Timer(const Duration(milliseconds: 800), () {
      unawaited(pushSkill(store));
    });
  }

  Future<void> pushFocus(Map<String, dynamic> store) async {
    final client = _client;
    final uid = _uid;
    if (client == null || uid == null || !serverAvailable) return;
    final sw = Stopwatch()..start();
    var ok = false;
    try {
      final result = await client.pushPracticeFocusSync(store);
      if (!result.available || result.store == null) return;
      final merged = parseFocusPracticeHistory(jsonEncode(result.store));
      final disk = PrefsFocusPracticeStore();
      await disk.writeRaw(uid, serializeFocusPracticeHistory(merged));
      ok = true;
    } catch (_) {
      // soft fail
    } finally {
      sw.stop();
      asrEvidenceBus?.record(
        'practice_focus_sync',
        severity: 'lifecycle',
        ok: ok,
        details: {'op': 'push', 'elapsed_ms': sw.elapsedMilliseconds},
      );
    }
  }

  Future<void> pushSkill(Map<String, dynamic> store) async {
    final client = _client;
    final uid = _uid;
    if (client == null || uid == null || !serverAvailable) return;
    final sw = Stopwatch()..start();
    var ok = false;
    try {
      final result = await client.pushPracticeSkillSync(store);
      if (!result.available || result.store == null) return;
      final merged = SkillState.fromJson(result.store!);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(skillPrefsKey(uid), jsonEncode(merged.toJson()));
      ok = true;
    } catch (_) {
      // soft fail
    } finally {
      sw.stop();
      asrEvidenceBus?.record(
        'practice_skill_sync',
        severity: 'lifecycle',
        ok: ok,
        details: {'op': 'push', 'elapsed_ms': sw.elapsedMilliseconds},
      );
    }
  }
}

/// App-root singleton (set from [SentenceReadingApp]).
PracticeCloudSync? asrPracticeCloudSync;
