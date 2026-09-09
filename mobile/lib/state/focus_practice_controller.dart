/// design/176 — 10‑min speaking focus clock (plan C: mic speak segments only).
/// Calendar history + streak; give-up resets unfinished block only.
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
  FocusPracticeHistory _history = const FocusPracticeHistory();
  FocusPracticeDayState _day = FocusPracticeDayState(day: focusPracticeDayKey());

  bool sessionActive = false;
  bool paused = false;
  bool speaking = false;

  /// Progress inside the current unfinished block (not persisted).
  Duration elapsedInBlock = Duration.zero;

  DateTime? _speakStartedAt;
  Timer? _uiTick;

  FocusPracticeHistory get history => _history;
  FocusPracticeDayState get dayState => _day;
  bool get daySuccess => _day.success;
  int get blocksCompletedToday => _day.blocksCompleted;

  int get currentStreak => computeFocusCurrentStreak(
        _history.days,
        todayKey: focusPracticeDayKey(_clock()),
      );

  int get bestStreak {
    final cur = currentStreak;
    return cur > _history.bestStreak ? cur : _history.bestStreak;
  }

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
      _history = parseFocusPracticeHistory(raw);
    } catch (_) {
      _history = const FocusPracticeHistory();
    }
    _syncTodayFromHistory();
    notifyListeners();
  }

  void _syncTodayFromHistory() {
    final today = focusPracticeDayKey(_clock());
    _day = _history.dayStateFor(today);
  }

  Future<void> _persist() async {
    _syncTodayFromHistory();
    final cur = currentStreak;
    if (cur > _history.bestStreak) {
      _history = _history.copyWith(bestStreak: cur);
    }
    try {
      await _store.writeRaw(_uid, serializeFocusPracticeHistory(_history));
    } catch (_) {
      // EDGE: prefs fail — keep memory state; next bind may miss.
    }
  }

  void startSession({String? cacheId}) {
    _syncTodayFromHistory();
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
        'current_streak': currentStreak,
      },
    );
    _armUiTick();
    notifyListeners();
  }

  /// 집중 끝내기 — keep earned blocks/day success; wipe unfinished block clock.
  void giveUp({String? cacheId}) {
    if (speaking) {
      endSpeak(cacheId: cacheId);
    }
    final was = sessionActive;
    final abandonedMs = elapsedInBlock.inMilliseconds;
    sessionActive = false;
    paused = false;
    elapsedInBlock = Duration.zero;
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
          'elapsed_in_block_ms': abandonedMs,
          'block_reset': 1,
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

  /// App lifecycle — foreground-only clock (design/176). Does **not** reset block.
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
    _syncTodayFromHistory();
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
        final today = focusPracticeDayKey(_clock());
        final prevBlocks = _history.blocksFor(today);
        final nextBlocks = prevBlocks + 1;
        final days = Map<String, int>.from(_history.days);
        days[today] = nextBlocks;
        final first = prevBlocks <= 0;
        _history = _history.copyWith(days: days);
        _day = FocusPracticeDayState(
          day: today,
          success: true,
          blocksCompleted: nextBlocks,
        );
        unawaited(_persist());
        asrEvidenceBus?.record(
          'focus_block_done',
          cacheId: cacheId ?? '',
          severity: 'boundary',
          ok: true,
          details: {
            'day_ymd': int.tryParse(today.replaceAll('-', '')) ?? 0,
            'blocks_completed': nextBlocks,
            'first_success_today': first,
            'current_streak': currentStreak,
          },
        );
        if (first) {
          asrEvidenceBus?.record(
            'focus_day_success',
            cacheId: cacheId ?? '',
            severity: 'boundary',
            ok: true,
            details: {
              'day_ymd': int.tryParse(today.replaceAll('-', '')) ?? 0,
              'blocks_completed': nextBlocks,
              'current_streak': currentStreak,
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
