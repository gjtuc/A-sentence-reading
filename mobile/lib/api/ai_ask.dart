/// Run AI ask: open Google AI Mode with the question (design/419), or copy it
/// and open Google AI when it does not fit an address (design/182).
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/ai_window.dart';
import '../services/figure_clipboard.dart';
import 'ai_ask_prompt_models.dart';

/// design/432 — the web opens its own AI window; the phone hands off to the app.
Future<bool> _openAi(Uri uri) async {
  if (kIsWeb && openAiWindow(uri)) return true;
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}

class AiAskLaunchResult {
  const AiAskLaunchResult({
    required this.copied,
    required this.launched,
    this.direct = false,
  });

  final bool copied;
  final bool launched;

  /// The question went in the address; nothing to paste.
  final bool direct;
}

Future<AiAskLaunchResult> runAiAsk({
  required String sentencePlain,
  required String promptBody,
}) async {
  final body = promptBody.trim();
  if (body.isEmpty) {
    return const AiAskLaunchResult(copied: false, launched: false);
  }
  final direct = aiAskModeUri(sentencePlain: sentencePlain, promptBody: body);
  if (direct != null) {
    try {
      if (await _openAi(direct)) {
        return const AiAskLaunchResult(copied: false, launched: true, direct: true);
      }
    } catch (_) {}
  }
  final payload = buildAiAskClipboard(
    sentencePlain: sentencePlain,
    promptBody: body,
  );
  await Clipboard.setData(ClipboardData(text: payload));
  var launched = false;
  try {
    launched = await _openAi(Uri.parse(kAiAskGoogleUrl));
  } catch (_) {
    launched = false;
  }
  return AiAskLaunchResult(copied: true, launched: launched);
}

/// design/434 — a figure cannot travel in the address, so it is pasted: the
/// question (if any) and then the picture go to the clipboard, then the AI page
/// opens empty.
Future<AiAskLaunchResult> runFigureAiAsk({
  required Uint8List image,
  required String mime,
  String question = '',
}) async {
  final copied = await copyFigureForAi(image, mime: mime, question: question);
  if (!copied) return const AiAskLaunchResult(copied: false, launched: false);
  var launched = false;
  try {
    launched = await _openAi(Uri.parse(kAiAskGoogleUrl));
  } catch (_) {
    launched = false;
  }
  return AiAskLaunchResult(copied: true, launched: launched);
}
