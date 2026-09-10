/// design/214 — minimal rhythm stage tokens (practice mode only).
library;

import 'package:flutter/material.dart';

const Color kRhythmStage = Color(0xFF121212);
const Color kRhythmRailIdle = Color(0xFF333333);
const Color kRhythmListen = Color(0xFF8E8E8E);
const Color kRhythmSpeak = Color(0xFF5B9FD4);
const Color kRhythmReplay = Color(0xFF6B6B6B);
const Color kRhythmGood = Color(0xFFE8B84A);
const Color kRhythmGreat = Color(0xFF6BCB8A);
const Color kRhythmPerfect = Color(0xFFF0C14B);
const Color kRhythmText = Color(0xFFFFFFFF);
const Color kRhythmTextMuted = Color(0xFFB0B0B0);

const Duration kJudgmentPop = Duration(milliseconds: 220);
const Duration kJudgmentHoldGood = Duration(milliseconds: 700);
const Duration kJudgmentHoldGreat = Duration(milliseconds: 900);
const Duration kJudgmentHoldPerfect = Duration(milliseconds: 1100);
const Duration kJudgmentFade = Duration(milliseconds: 260);

enum RhythmPhase { idle, listen, speak, replay }

Color rhythmAccentFor(RhythmPhase phase) {
  switch (phase) {
    case RhythmPhase.listen:
      return kRhythmListen;
    case RhythmPhase.speak:
      return kRhythmSpeak;
    case RhythmPhase.replay:
      return kRhythmReplay;
    case RhythmPhase.idle:
      return kRhythmRailIdle;
  }
}
