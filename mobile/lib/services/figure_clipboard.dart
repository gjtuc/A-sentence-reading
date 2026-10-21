/// design/434 - the figure (and its question) onto the clipboard for the AI page.
library;

import 'dart:typed_data';

import 'figure_clipboard_stub.dart'
    if (dart.library.js_interop) 'figure_clipboard_web.dart' as impl;

/// Windows' clipboard history keeps each copy as its own entry only when they
/// are apart; 800 ms was the gap measured to leave both in Win+V.
const Duration kFigureQuestionGap = Duration(milliseconds: 800);

/// Copies [question] (when not empty), then the picture, so the picture is what
/// Ctrl+V pastes. False off the web or when the browser refused.
Future<bool> copyFigureForAi(
  Uint8List bytes, {
  required String mime,
  String question = '',
}) {
  return impl.copy(bytes, mime, question.trim(), kFigureQuestionGap);
}
