/// Run AI ask: open Google AI Mode with the question (design/419), or copy it
/// and open Google AI when it does not fit an address (design/182).
library;

import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'ai_ask_prompt_models.dart';

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
      if (await launchUrl(direct, mode: LaunchMode.externalApplication)) {
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
    launched = await launchUrl(
      Uri.parse(kAiAskGoogleUrl),
      mode: LaunchMode.externalApplication,
    );
  } catch (_) {
    launched = false;
  }
  return AiAskLaunchResult(copied: true, launched: launched);
}
