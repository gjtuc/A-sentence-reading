/// design/176 — 10‑min speaking focus clock (plan C: mic speak segments only).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/focus_practice_models.dart';
import '../api/focus_practice_store.dart';
import '../services/evidence_bus.dart';

class FocusPracticeController extends ChangeNotifier {
  FocusPracticeController({
    FocusPracticeStore? store,
    this.blockDuration = kFocusPracticeBlockDuration,
    DateTime Function()? clock,
  })  : _store = store ?? PrefsFocusPracticeStore(),
        _clock = clock ?? DateTime.now;

  final FocusPracticeStore _store;
  final Duration blockDuration;
  final DateTime Function() _clock;

  String? _uid;
  FocusPracticeDayState _day = FocusPracticeDayState(day: focusPracticeDayKey());

  bool sessionActive = false;
  bool paused = false;
  bool speaking = false;

  /// Completed portion of the current block (persisted only via day counters).
  Duration elapsedInBlock = Duration.zero;

  DateTime? _speakStartedAt;
  Timer? _uiTick;

  FocusPracticeDayState get dayState => _day;
  bool get daySuccess => _day.success;
  int get blocksCompletedToday => _day.blocksCompleted;

  /// Live display: committed elapsed + open speak segment.
  Duration get displayElapsed {
    var e = elapsedInBlock;
    final start = _speakStartedAt;
    if (speaking && !paused && start != null) {
      e += _clock().difference(start);
    }
    if (e > blockDuration) return blockDuration;
    if (e.isNegative) return Duration.zero;
    return e;
  }

  Duration get displayRemaining {
    final left = blockDuration - displayElapsed;
    return left.isNegative ? Duration.zero : left;
  }

  String get elapsedLabel => formatFocusClock(displayElapsed);
  String get remainingLabel => formatFocusClock(displayRemaining);

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    try {
      final raw = await _store.readRaw(_uid);
      _day = parseFocusPracticeDayState(raw);
    } catch (_) {
      _day = FocusPracticeDayState(day: focusPracticeDayKey(_clock()));
    }
    _ensureToday();
    notifyListeners();
  }

  void _ensureToday() {
    final today = focusPracticeDayKey(_clock());
    if (_day.day != today) {
      _day = FocusPracticeDayState(day: today);
    }
  }

  Future<void> _persist() async {
    _ensureToday();
    try {
      await _store.writeRaw(_uid, serializeFocusPracticeDayState(_day));
    } catch (_) {
      // EDGE: prefs fail — keep memory state; next bind may miss.
    }
  }

  void startSession({String? cacheId}) {
    _ensureToday();
    if (sessionActive && !paused) return;
    sessionActive = true;
    paused = false;
    asrEvidenceBus?.record(
      'focus_session_start',
      cacheId: cacheId ?? '',
      severity: 'lifecycle',
      ok: true,
      details: {
        'day_ymd': int.tryParse(_day.day.replaceAll('-', '')) ?? 0,
        'blocks_completed': _day.blocksCompleted,
        'day_success': _day.success,
      },
    );
    _armUiTick();
    notifyListeners();
  }

  /// GIVE UP — stop session; keep today's success/blocks.
  void giveUp({String? cacheId}) {
    if (speaking) {
      endSpeak(cacheId: cacheId);
    }
    final was = sessionActive;
    sessionActive = false;
    paused = false;
    _cancelUiTick();
    if (was) {
      asrEvidenceBus?.record(
        'focus_session_end',
        cacheId: cacheId ?? '',
        severity: 'lifecycle',
        ok: true,
        details: {
          'reason': 'give_up',
          'day_ymd': int.tryParse(_day.day.replaceAll('-', '')) ?? 0,
          'blocks_completed': _day.blocksCompleted,
          'day_success': _day.success,
          'elapsed_in_block_ms': elapsedInBlock.inMilliseconds,
        },
      );
    }
    notifyListeners();
  }

  void pause({String? cacheId}) {
    if (!sessionActive || paused) return;
    if (speaking) {
      endSpeak(cacheId: cacheId);
    }
    paused = true;
    _cancelUiTick();
    notifyListeners();
  }

  void resume() {
    if (!sessionActive || !paused) return;
    paused = false;
    _armUiTick();
    notifyListeners();
  }

  /// App lifecycle — foreground-only clock (design/176).
  void onAppPaused({String? cacheId}) => pause(cacheId: cacheId);

  void beginSpeak() {
    if (!sessionActive || paused) return;
    if (speaking) return;
    speaking = true;
    _speakStartedAt = _clock();
    _armUiTick();
    notifyListeners();
  }

  void endSpeak({String? cacheId}) {
    if (!speaking) return;
    final start = _speakStartedAt;
    speaking = false;
    _speakStartedAt = null;
    if (start != null && sessionActive && !paused) {
      final delta = _clock().difference(start);
      if (!delta.isNegative && delta > Duration.zero) {
        _addElapsed(delta, cacheId: cacheId);
      }
    }
    notifyListeners();
  }

  void _addElapsed(Duration delta, {String? cacheId}) {
    _ensureToday();
    var left = delta;
    while (left > Duration.zero) {
      final room = blockDuration - elapsedInBlock;
      if (room <= Duration.zero) {
        elapsedInBlock = Duration.zero;
        continue;
      }
      if (left >= room) {
        left -= room;
        elapsedInBlock = Duration.zero;
        final first = !_day.success;
        _day = _day.copyWith(
          success: true,
          blocksCompleted: _day.blocksCompleted + 1,
        );
        unawaited(_persist());
        asrEvidenceBus?.record(
          'focus_block_done',
          cacheId: cacheId ?? '',
          severity: 'boundary',
          ok: true,
          details: {
            'day_ymd': int.tryParse(_day.day.replaceAll('-', '')) ?? 0,
            'blocks_completed': _day.blocksCompleted,
            'first_success_today': first,
          },
        );
        if (first) {
          asrEvidenceBus?.record(
            'focus_day_success',
            cacheId: cacheId ?? '',
            severity: 'boundary',
            ok: true,
            details: {
              'day_ymd': int.tryParse(_day.day.replaceAll('-', '')) ?? 0,
              'blocks_completed': _day.blocksCompleted,
            },
          );
        }
      } else {
        elapsedInBlock += left;
        left = Duration.zero;
      }
    }
  }

  void _armUiTick() {
    _uiTick?.cancel();
    if (!sessionActive || paused) return;
    _uiTick = Timer.periodic(const Duration(milliseconds: 200), (_) {
      if (speaking) notifyListeners();
    });
  }

  void _cancelUiTick() {
    _uiTick?.cancel();
    _uiTick = null;
  }

  @override
  void dispose() {
    _cancelUiTick();
    super.dispose();
  }
}
