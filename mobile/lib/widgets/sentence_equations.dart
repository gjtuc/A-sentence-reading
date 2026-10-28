import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/reading_models.dart';

/// design/481 — the paper's body type, in points. An equation picture is scaled so
/// its letters read at the sentence's size: a 9.5 pt page line becomes one line here.
const double kEquationPagePt = 9.5;

/// Gray page pictures redrawn in the reader's colours: white becomes [paper],
/// black becomes [ink], and gray falls between them.
ColorFilter equationTint({required Color ink, required Color paper}) {
  List<double> row(double i, double p) => [p - i, 0, 0, 0, i * 255];
  return ColorFilter.matrix([
    ...row(ink.r, paper.r),
    ...row(ink.g, paper.g),
    ...row(ink.b, paper.b),
    0, 0, 0, 1, 0,
  ]);
}

/// Width an equation [w] points wide wants at [fontSize]; a narrower column shrinks it.
double equationWidth(EquationView eq, {required double fontSize}) =>
    eq.w * fontSize / kEquationPagePt;

const int _kBytesCacheSize = 24;
final List<(String, Uint8List?)> _bytesCache = [];

/// The same bytes for the same picture on every rebuild, so it never blinks.
Uint8List? _equationBytes(String src) {
  for (var i = 0; i < _bytesCache.length; i++) {
    final (key, value) = _bytesCache[i];
    if (identical(key, src) || key == src) {
      if (i > 0) _bytesCache.insert(0, _bytesCache.removeAt(i));
      return value;
    }
  }
  Uint8List? bytes;
  final comma = src.indexOf(',');
  if (comma > 0) {
    try {
      bytes = base64Decode(src.substring(comma + 1));
    } catch (_) {
      bytes = null;
    }
  }
  _bytesCache.insert(0, (src, bytes));
  if (_bytesCache.length > _kBytesCacheSize) _bytesCache.removeLast();
  return bytes;
}

/// The display equations that follow a sentence, one under another.
class SentenceEquations extends StatelessWidget {
  const SentenceEquations({super.key, required this.equations, required this.style});

  final List<EquationView> equations;

  /// The sentence's style: its size scales the pictures, its colour inks them.
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final ink = style.color ?? theme.colorScheme.onSurface;
    final paper = theme.cardTheme.color ?? theme.colorScheme.surfaceContainerLow;
    final fontSize = style.fontSize ?? 18;
    final tint = equationTint(ink: ink, paper: paper);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final eq in equations)
          if (_equationBytes(eq.src) case final Uint8List bytes)
            Padding(
              key: ValueKey('equation-${eq.id}'),
              padding: EdgeInsets.only(top: fontSize * 0.6),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: equationWidth(eq, fontSize: fontSize),
                  ),
                  child: AspectRatio(
                    aspectRatio: eq.w / eq.h,
                    child: ExcludeSemantics(
                      child: ColorFiltered(
                        colorFilter: tint,
                        child: Image.memory(
                          bytes,
                          fit: BoxFit.fill,
                          filterQuality: FilterQuality.medium,
                          gaplessPlayback: true,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
      ],
    );
  }
}
