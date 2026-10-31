/// design/500 — a rough caption while a question is spoken. The browser's own
/// speech recognition writes it for free as the words come; it is only there
/// to show the question is being heard. The recording is still written down
/// once at the end with the sentence on screen (design/475), and that text is
/// what lands in the box.
library;

import 'live_caption_stub.dart' if (dart.library.js_interop) 'live_caption_web.dart'
    as impl;

/// Ends a running caption. Safe to call more than once.
typedef LiveCaptionStop = void Function();

/// [onText] gets the whole caption so far each time it changes. Null where
/// there is no free recognizer: the phone app for now, and Firefox.
typedef LiveCaptionStart = LiveCaptionStop? Function(void Function(String text) onText);

LiveCaptionStop? startLiveCaption(void Function(String text) onText) => impl.start(onText);

/// Chrome ends a long take on its own and starts over with empty results, so
/// the words of the earlier rounds are kept in front.
String liveCaptionJoin(String kept, String now) =>
    '$kept $now'.replaceAll(RegExp(r'\s+'), ' ').trim();

/// A long question shows its latest words, which are the ones just said.
String liveCaptionTail(String text, {int max = 120}) =>
    text.length <= max ? text : '…${text.substring(text.length - max).trimLeft()}';
