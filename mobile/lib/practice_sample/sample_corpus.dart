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
///
/// Replaced wholesale at seed version 2: the first set was spent in one sitting
/// when a round had no end, so every line in it had already been read once.
const List<SampleLine> kSampleFreshLines = [
  SampleLine(
    id: 'n01',
    marked: 'A Tafel slope of 42 mV/dec | indicated a rate-determining | '
        'first electron transfer.',
    note: 'tafel_slope_per_decade',
  ),
  SampleLine(
    id: 'n02',
    marked: 'The (111) reflection at 2θ = 43.6° | broadened as | '
        'the crystallite size fell.',
    note: 'two_theta_and_miller_index',
  ),
  SampleLine(
    id: 'n03',
    marked: 'Scherrer analysis gave | a crystallite size of 8.4 ± 0.6 nm | '
        'for the calcined powder.',
    note: 'plus_minus_tolerance',
  ),
  SampleLine(
    id: 'n04',
    marked: 'Extended X-ray absorption fine structure | '
        'resolved a Ni–O coordination number | of 4.2.',
    note: 'long_technique_en_dash',
  ),
  SampleLine(
    id: 'n05',
    marked: 'A gas hourly space velocity of 24,000 mL/g/h | was held | '
        'for the entire run.',
    note: 'thousands_comma_and_stacked_unit',
  ),
  SampleLine(
    id: 'n06',
    marked: 'Sulfur was kept below 50 ppm | to avoid | '
        'irreversible poisoning.',
    note: 'ppm_and_hard_word',
  ),
  SampleLine(
    id: 'n07',
    marked: 'Ostwald ripening coarsened the particles, | '
        'whereas encapsulation | suppressed coalescence.',
    note: 'eponym_and_contrast_clause',
  ),
  SampleLine(
    id: 'n08',
    marked: 'The kinetics followed | a Mars–van Krevelen mechanism | '
        'rather than Langmuir–Hinshelwood.',
    note: 'two_eponym_mechanisms',
  ),
  SampleLine(
    id: 'n09',
    marked: 'The area-specific resistance rose | to 0.31 Ω cm² | '
        'after five hundred hours.',
    note: 'ohm_cm_squared',
  ),
  SampleLine(
    id: 'n10',
    marked: 'Diffraction used Cu Kα radiation | with λ = 1.5406 Å | '
        'at room temperature.',
    note: 'greek_lambda_and_angstrom',
  ),
  SampleLine(
    id: 'n11',
    marked: 'The adsorption enthalpy ΔH | was −78 kJ/mol | '
        'on the stepped facet.',
    note: 'delta_h_negative',
  ),
  SampleLine(
    id: 'n12',
    marked: 'Electrical conductivity reached | 3.6 × 10⁻² S/cm | '
        'after carbonisation.',
    note: 'scientific_notation_times',
  ),
  SampleLine(
    id: 'n13',
    marked: 'Operando DRIFTS detected | a bridging carbonate band | '
        'at 1580 cm⁻¹.',
    note: 'wavenumber_inverse_cm',
  ),
  SampleLine(
    id: 'n14',
    marked: 'Isotopic labelling with ¹³CH4 | '
        'confirmed that lattice carbon | entered the product.',
    note: 'isotope_superscript_prefix',
  ),
  SampleLine(
    id: 'n15',
    marked: 'The reverse water-gas shift (RWGS) | consumed hydrogen | '
        'above 700 °C.',
    note: 'defined_abbreviation_hyphen_chain',
  ),
  SampleLine(
    id: 'n16',
    marked: 'NH3-TPD quantified | 0.42 mmol/g of | '
        'moderately strong acid sites.',
    note: 'formula_prefixed_technique',
  ),
  SampleLine(
    id: 'n17',
    marked: 'BJH analysis showed | a bimodal pore distribution | '
        'centred near 4 and 19 nm.',
    note: 'two_values_one_unit',
  ),
  SampleLine(
    id: 'n18',
    marked: 'Electrochemical impedance spectroscopy | '
        'produced a depressed Nyquist semicircle | on the aged electrode.',
    note: 'long_technique_and_eponym',
  ),
  SampleLine(
    id: 'n19',
    marked: 'Rietveld refinement converged | with χ² of 1.7 | '
        'and a weighted R-factor of 4.9%.',
    note: 'chi_squared_and_r_factor',
  ),
  SampleLine(
    id: 'n20',
    marked: 'Single-atom alloys (SAA) | dissociated methane | '
        'without extensive coke formation.',
    note: 'abbreviation_and_negation',
  ),
  SampleLine(
    id: 'n21',
    marked: 'Multiwalled carbon nanotubes grew | '
        'from coordinatively unsaturated | nickel step edges.',
    note: 'hard_adjective_phrase',
  ),
  SampleLine(
    id: 'n22',
    marked: 'The double-layer capacitance was | 28 μF/cm² | '
        'in one molar potassium hydroxide.',
    note: 'micro_farad_per_cm2',
  ),
  SampleLine(
    id: 'n23',
    marked: 'Selectivity toward ethylene | exceeded 71%, | '
        'whereas methane stayed below 3%.',
    note: 'two_percentages_contrast',
  ),
  SampleLine(
    id: 'n24',
    marked: 'Micrographs recorded at 200,000× | resolved lattice fringes | '
        'across the shell.',
    note: 'magnification_times_sign',
  ),
  SampleLine(
    id: 'n25',
    marked: 'Pyrolysis proceeded at 5 °C/min | under flowing argon | '
        'to 900 °C.',
    note: 'ramp_rate_per_minute',
  ),
  SampleLine(
    id: 'n26',
    marked: 'The isotherm showed type IV hysteresis, | consistent with | '
        'high pore tortuosity.',
    note: 'roman_numeral_type',
  ),
  SampleLine(
    id: 'n27',
    marked: 'Density functional calculations placed | the d-band centre | '
        'at −1.84 eV.',
    note: 'd_band_and_negative_ev',
  ),
  SampleLine(
    id: 'n28',
    marked: 'The Sabatier principle predicts | an optimum binding strength, | '
        'neither too weak nor too strong.',
    note: 'eponym_and_long_clause',
  ),
  SampleLine(
    id: 'n29',
    marked: 'Anisotropic growth established | a percolating network | '
        'above 12 vol%.',
    note: 'vol_percent',
  ),
  SampleLine(
    id: 'n30',
    marked: 'The half-wave potential improved by 60 mV | '
        'after cobalt substitution, | which lowered the overpotential.',
    note: 'mv_and_overpotential',
  ),
];

/// Fresh lines per round.
const int kSampleFreshPerRound = 3;

/// Sentences one round reads. The round ends here, so practice can stop.
const int kSampleRoundLineCount = 12 + kSampleFreshPerRound;

/// Fresh lines for one round, three per difficulty, never reused.
List<SampleLine> sampleFreshForRound(int round) {
  final r = round.clamp(1, kSampleRoundCount);
  final start = (r - 1) * kSampleFreshPerRound;
  if (start >= kSampleFreshLines.length) return const [];
  final end = (start + kSampleFreshPerRound).clamp(0, kSampleFreshLines.length);
  return kSampleFreshLines.sublist(start, end);
}

/// Everything a round reads: the twelve fixed lines then that round's three.
List<SampleLine> sampleLinesForRound(int round) => [
      ...kSampleFixedLines,
      ...sampleFreshForRound(round),
    ];

/// Every line the sample row holds, for the chunk plan.
List<SampleLine> get sampleAllLines => [
      ...kSampleFixedLines,
      ...kSampleFreshLines,
    ];
