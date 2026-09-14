/// design/283 — client-side ingest stage N/M regress / loop tracker.
library;

class IngestStagePassSlot {
  int passN = 0;
  int lastOutN = -1;
  int lastInN = 0;
  int tickN = 0;
}

/// Parses upload badge text like 「서론 재감수 12/135」 into tokens + counters.
class IngestStageFraction {
  const IngestStageFraction({
    required this.section,
    required this.phase,
    required this.outN,
    required this.inN,
  });

  final String section;
  final String phase;
  final int outN;
  final int inN;
}

IngestStageFraction? parseIngestStageFraction(String stage) {
  final s = stage.trim();
  if (s.isEmpty) return null;
  // Prefer the segment that still has N/M (progress badge often has · parts).
  final parts = s.split('·').map((e) => e.trim()).where((e) => e.isNotEmpty);
  String? hit;
  for (final p in parts) {
    if (RegExp(r'\d+\s*/\s*\d+').hasMatch(p)) {
      hit = p;
      break;
    }
  }
  hit ??= s;
  final m = RegExp(r'(\d+)\s*/\s*(\d+)').firstMatch(hit);
  if (m == null) return null;
  final outN = int.tryParse(m.group(1) ?? '') ?? -1;
  final inN = int.tryParse(m.group(2) ?? '') ?? -1;
  if (outN < 0 || inN <= 0) return null;
  final phase = _phaseToken(hit);
  final section = _sectionToken(hit);
  return IngestStageFraction(
    section: section,
    phase: phase,
    outN: outN,
    inN: inN,
  );
}

String _phaseToken(String raw) {
  if (raw.contains('재감수')) return 'harmonize';
  if (raw.contains('요지')) return 'digest';
  if (raw.contains('캡션')) return 'caption';
  if (raw.contains('번역')) return 'translate';
  return 'other';
}

String _sectionToken(String raw) {
  // Korean UI labels from translate_section._sec_label — map to snake.
  if (raw.contains('서론') || raw.contains('Introduction')) return 'introduction';
  if (raw.contains('초록') || raw.contains('Abstract')) return 'abstract';
  if (raw.contains('결론') || raw.contains('Conclusion')) return 'conclusion';
  if (raw.contains('결과') || raw.contains('Result')) return 'results';
  if (raw.contains('실험') || raw.contains('Experimental')) return 'experimental';
  if (raw.contains('토론') || raw.contains('Discussion')) return 'discussion';
  if (raw.contains('방법') || raw.contains('Method')) return 'methods';
  if (raw.contains('본문') || raw.contains('body')) return 'body';
  return 'unknown';
}

/// Mutable tracker keyed by section|phase for one upload session.
class IngestStagePassTracker {
  final Map<String, IngestStagePassSlot> _slots = {};

  void reset() => _slots.clear();

  String _key(String section, String phase) => '$section|$phase';

  /// Returns events to emit (kind + details). Empty if nothing notable.
  List<({String kind, String severity, bool ok, Map<String, Object?> details})>
      noteFraction(IngestStageFraction frac, {int? percent}) {
    final key = _key(frac.section, frac.phase);
    final slot = _slots.putIfAbsent(key, IngestStagePassSlot.new);
    final events =
        <({String kind, String severity, bool ok, Map<String, Object?> details})>[];

    var regress = false;
    if (slot.lastOutN >= 0 && frac.outN < slot.lastOutN) {
      regress = true;
    }
    if (slot.lastOutN >= 0 &&
        slot.lastInN > 0 &&
        slot.lastOutN >= (0.8 * slot.lastInN).floor() &&
        frac.outN <= (0.2 * frac.inN).ceil()) {
      regress = true;
    }

    if (regress) {
      // Restart into a new pass.
      slot.passN = slot.passN < 1 ? 2 : slot.passN + 1;
      events.add((
        kind: 'ingest_progress_regress',
        severity: 'error',
        ok: false,
        details: {
          'section': frac.section,
          'phase': frac.phase,
          'pass_n': slot.passN,
          'prev_out_n': slot.lastOutN,
          'out_n': frac.outN,
          'in_n': frac.inN,
          if (percent != null) 'percent': percent,
        },
      ));
      if (slot.passN >= 2) {
        events.add((
          kind: 'ingest_stage_loop',
          severity: slot.passN >= 3 ? 'error' : 'lifecycle',
          ok: false,
          details: {
            'section': frac.section,
            'phase': frac.phase,
            'pass_n': slot.passN,
            'out_n': frac.outN,
            'in_n': frac.inN,
            if (percent != null) 'percent': percent,
          },
        ));
      }
    } else if (slot.passN < 1) {
      slot.passN = 1;
    }

    slot.lastOutN = frac.outN;
    slot.lastInN = frac.inN;
    slot.tickN += 1;

    final sample = slot.tickN == 1 ||
        frac.outN == 1 ||
        frac.outN % 10 == 0 ||
        frac.outN == frac.inN;
    if (sample) {
      events.add((
        kind: 'ingest_stage_tick',
        severity: 'lifecycle',
        ok: true,
        details: {
          'section': frac.section,
          'phase': frac.phase,
          'pass_n': slot.passN < 1 ? 1 : slot.passN,
          'out_n': frac.outN,
          'in_n': frac.inN,
          if (percent != null) 'percent': percent,
        },
      ));
    }
    return events;
  }
}
