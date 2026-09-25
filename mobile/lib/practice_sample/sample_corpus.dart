/// design/364 — fixed pronunciation sample corpus (calibration source).
///
/// Paper sentences change every session, so a score that moved cannot say
/// whether the scoring changed or the text did. These lines never change, so
/// one take can be re-scored after every threshold edit and compared.
library;

/// Cache id for the sample row. Alphanumeric 8..32 so server helpers accept it.
const String kSampleCacheId = 'asrpronsamplev1';

const String kSampleTitle = '발음 표본';

/// Difficulty rounds on the sample row (ladder tier 0..9 shown as 1..10).
const int kSampleRoundCount = 10;

/// Break marker inside a sample line.
///
/// Counting words by hand is how chunk lists go silently wrong, so the break
/// points live in the text itself.
const String kSampleBreak = '|';

class SampleLine {
  const SampleLine({
    required this.id,
    required this.marked,
    this.note = '',
  });

  final String id;

  /// Sentence with [kSampleBreak] at every practice step boundary.
  final String marked;

  /// Why the line is in the set, for the corpus test and for review.
  final String note;

  List<String> get segments => [
        for (final part in marked.split(kSampleBreak))
          if (part.trim().isNotEmpty) part.trim(),
      ];

  String get text => segments.join(' ');

  /// Growing prefixes, last one the whole sentence (server chunk convention).
  List<String> get chunks {
    final out = <String>[];
    final buf = <String>[];
    for (final part in segments) {
      buf.add(part);
      out.add(buf.join(' '));
    }
    return out;
  }
}

/// Read at every difficulty, so the ladder is the only thing that varies.
///
/// Twelve lines ten times will be memorised. That is accepted here: with the
/// text held still, a score that moves is the scoring moving.
const List<SampleLine> kSampleFixedLines = [
  SampleLine(
    id: 'f01',
    marked: 'The nickel catalyst | remained active throughout | '
        'the reforming experiment.',
    note: 'baseline_no_symbols',
  ),
  SampleLine(
    id: 'f02',
    marked: 'Chemical vapour deposition (CVD) | produced a graphitic shell | '
        'around every particle.',
    note: 'defined_abbreviation',
  ),
  SampleLine(
    id: 'f03',
    marked: 'The mean particle size | grew from 2.3 nm | to 15 nm | '
        'after reduction.',
    note: 'unit_nm_and_decimals',
  ),
  SampleLine(
    id: 'f04',
    marked: 'Methane and CO2 were fed | at a molar ratio | of 1.2 to 1.',
    note: 'formula_and_ratio',
  ),
  SampleLine(
    id: 'f05',
    marked: 'The alpha alumina phase | appeared only above | 900 °C.',
    note: 'greek_spelled_and_degrees',
  ),
  SampleLine(
    id: 'f06',
    marked: 'The Ni 2p binding energy | shifted by 0.4 eV | after reduction.',
    note: 'orbital_label_and_ev',
  ),
  SampleLine(
    id: 'f07',
    marked: 'The thickness of the third layer | was then measured | '
        'by ellipsometry.',
    note: 'th_cluster',
  ),
  SampleLine(
    id: 'f08',
    marked: 'The reduced surface | slowly released chlorine | '
        'during the early rinse.',
    note: 'r_and_l',
  ),
  SampleLine(
    id: 'f09',
    marked: 'Vanadium vapour was absorbed | by the porous | carbon bed.',
    note: 'v_and_b',
  ),
  SampleLine(
    id: 'f10',
    marked: 'Although the catalyst deactivated, | '
        'catalytic activity recovered | after regeneration.',
    note: 'stress_shift',
  ),
  SampleLine(
    id: 'f11',
    marked: "Both catalysts' strengths | dropped sharply | at greater depths.",
    note: 'final_consonant_clusters',
  ),
  SampleLine(
    id: 'f12',
    marked: 'X-ray photoelectron spectroscopy showed | that the Ni 2p peak | '
        'shifted by 0.4 eV | after reduction at 600 °C.',
    note: 'long_compound_paper_style',
  ),
];

/// Three per difficulty, read once, so first-exposure difficulty stays real.
///
/// Without these the hard rounds would measure recall of a memorised line
/// instead of whether fast unfamiliar speech could be followed at all.
const List<SampleLine> kSampleFreshLines = [
  SampleLine(
    id: 'n01',
    marked: 'Turnover frequencies reached 4.7 s⁻¹ | at 750 °C | and 1 bar.',
    note: 'superscript_minus_one',
  ),
  SampleLine(
    id: 'n02',
    marked: 'High-resolution TEM revealed | 2.3 nm Pt–Co particles | '
        'encapsulated by three graphitic layers.',
    note: 'en_dash_alloy',
  ),
  SampleLine(
    id: 'n03',
    marked: 'Chemisorption indicated 38 μmol/g | of accessible nickel | '
        'on the reduced support.',
    note: 'greek_mu_unit',
  ),
  SampleLine(
    id: 'n04',
    marked: 'Coke deposition fell | from 18.6 to 2.4 mg/g/h | '
        'when 5 wt% Fe was added.',
    note: 'compound_rate_and_wt_percent',
  ),
  SampleLine(
    id: 'n05',
    marked: 'Dry reforming of methane (DRM) | converted 82% of the feed | '
        'at 800 °C.',
    note: 'defined_abbreviation_and_percent',
  ),
  SampleLine(
    id: 'n06',
    marked: 'The BET surface area | decreased from 142 to 97 m²/g | '
        'after calcination.',
    note: 'superscript_two_unit',
  ),
  SampleLine(
    id: 'n07',
    marked: 'Single-atom catalysts (SAC) | anchored isolated nickel | '
        'on nitrogen-doped carbon.',
    note: 'defined_abbreviation_hyphenated',
  ),
  SampleLine(
    id: 'n08',
    marked: 'X-ray absorption near-edge structure | '
        'confirmed an oxidation state | close to +2.',
    note: 'plus_sign_charge',
  ),
  SampleLine(
    id: 'n09',
    marked: 'Faradaic efficiency toward CO | exceeded 94% | at −0.8 V.',
    note: 'unicode_minus_voltage',
  ),
  SampleLine(
    id: 'n10',
    marked: 'Oxygen reduction activity peaked | at 0.89 V | '
        'versus the reversible hydrogen electrode.',
    note: 'volt_and_long_noun_phrase',
  ),
  SampleLine(
    id: 'n11',
    marked: 'Temperature-programmed reduction | showed two peaks, | '
        'at 420 and 680 °C.',
    note: 'hyphenated_technique',
  ),
  SampleLine(
    id: 'n12',
    marked: 'The lattice parameter contracted | by 0.9% | '
        'upon alloying with iron.',
    note: 'small_percent',
  ),
  SampleLine(
    id: 'n13',
    marked: 'Transmission electron microscopy (TEM) | '
        'showed a narrow size distribution | near 3 nm.',
    note: 'defined_abbreviation_long',
  ),
  SampleLine(
    id: 'n14',
    marked: 'Cyclic voltammetry at 50 mV/s | '
        'revealed a quasi-reversible couple | on the platinum surface.',
    note: 'rate_unit_per_second',
  ),
  SampleLine(
    id: 'n15',
    marked: 'The specific capacitance retained 91% | after ten thousand | '
        'charge–discharge cycles.',
    note: 'en_dash_compound',
  ),
  SampleLine(
    id: 'n16',
    marked: 'Inductively coupled plasma analysis | gave a nickel loading | '
        'of 11.3 wt%.',
    note: 'weight_percent',
  ),
  SampleLine(
    id: 'n17',
    marked: 'Thermogravimetric analysis showed | 7.8% mass loss | '
        'below 250 °C.',
    note: 'long_technique_name',
  ),
  SampleLine(
    id: 'n18',
    marked: 'The apparent activation energy | decreased from 96 | '
        'to 71 kJ/mol.',
    note: 'energy_per_mole',
  ),
  SampleLine(
    id: 'n19',
    marked: 'Density functional theory predicted | a carbon binding energy | '
        'of −6.2 eV.',
    note: 'unicode_minus_energy',
  ),
  SampleLine(
    id: 'n20',
    marked: 'Raman spectra showed | a D-to-G band intensity ratio | of 1.08.',
    note: 'letter_labels',
  ),
  SampleLine(
    id: 'n21',
    marked: 'The Ni–Fe–Al catalyst | was prepared by | '
        'solution combustion synthesis.',
    note: 'triple_en_dash_elements',
  ),
  SampleLine(
    id: 'n22',
    marked: 'The H2/CO ratio stayed | between 0.94 and 1.03 | '
        'throughout the run.',
    note: 'formula_slash_formula',
  ),
  SampleLine(
    id: 'n23',
    marked: 'Scanning transmission electron microscopy | '
        'resolved individual platinum atoms | on ceria.',
    note: 'four_word_technique',
  ),
  SampleLine(
    id: 'n24',
    marked: 'The catalyst sustained 120 hours on stream | '
        'without measurable | carbon whisker growth.',
    note: 'plain_numbers',
  ),
  SampleLine(
    id: 'n25',
    marked: 'In situ synchrotron diffraction | '
        'captured the reduction of NiO | to metallic nickel.',
    note: 'latin_phrase_and_formula',
  ),
  SampleLine(
    id: 'n26',
    marked: 'CO2-assisted ethane activation | gave 63% ethylene selectivity | '
        'over the bimetallic surface.',
    note: 'formula_leading_hyphen',
  ),
  SampleLine(
    id: 'n27',
    marked: 'The bimetallic surface segregated iron | '
        'under oxidising conditions | and reversed upon reduction.',
    note: 'long_clause_pair',
  ),
  SampleLine(
    id: 'n28',
    marked: 'BaCoO3 doping enhanced | the oxygen reduction reaction | '
        'at intermediate temperatures.',
    note: 'formula_leading_word',
  ),
  SampleLine(
    id: 'n29',
    marked: 'Graphene encapsulation preserved 3 nm particles | '
        'against sintering | for 500 hours.',
    note: 'unit_mid_phrase',
  ),
  SampleLine(
    id: 'n30',
    marked: 'The Ni 2p3/2 peak appeared | at 852.6 eV | '
        'after argon sputtering.',
    note: 'orbital_fraction_label',
  ),
];

/// Fresh lines for one round, three per difficulty, never reused.
List<SampleLine> sampleFreshForRound(int round) {
  final r = round.clamp(1, kSampleRoundCount);
  const per = 3;
  final start = (r - 1) * per;
  if (start >= kSampleFreshLines.length) return const [];
  final end = (start + per).clamp(0, kSampleFreshLines.length);
  return kSampleFreshLines.sublist(start, end);
}

/// Everything a round reads: the twelve fixed lines then that round's three.
List<SampleLine> sampleLinesForRound(int round) => [
      ...kSampleFixedLines,
      ...sampleFreshForRound(round),
    ];

/// Every line the sample row holds, for the session and the chunk plan.
List<SampleLine> get sampleAllLines => [
      ...kSampleFixedLines,
      ...kSampleFreshLines,
    ];
