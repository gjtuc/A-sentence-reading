/// Run AI ask: clipboard + open Google AI (design/182).
library;

import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'ai_ask_prompt_models.dart';

class AiAskLaunchResult {
  const AiAskLaunchResult({
    required this.copied,
    required this.launched,
  });

  final bool copied;
  final bool launched;
}

Future<AiAskLaunchResult> runAiAsk({
  required String sentencePlain,
  required String promptBody,
}) async {
  final body = promptBody.trim();
  if (body.isEmpty) {
    return const AiAskLaunchResult(copied: false, launched: false);
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
