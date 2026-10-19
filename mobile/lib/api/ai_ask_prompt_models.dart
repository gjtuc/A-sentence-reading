/// Local AI-ask prompt templates (design/182) — no server sync.
library;

const kAiAskPromptsPrefsKey = 'asr.ai_ask_prompts.v1';
const kAiAskSeededPrefsKey = 'asr.ai_ask_prompts.seeded_v1';

const kAiAskSeedPromptBody = '이 문장에 포함된 단어와 문법을 설명해줘.';

const kAiAskGoogleUrl = 'https://www.google.com/ai';

/// design/419 — Google AI Mode answers a question carried in the address, so
/// nothing has to be pasted. `udm=50` is not documented by Google; when it stops
/// working the copy-and-open path still stands.
const kAiAskModeUrl = 'https://www.google.com/search';

/// Longest address sent; a longer question falls back to the clipboard.
const kAiAskModeMaxUrl = 8000;

/// The question in one line: AI Mode drops line breaks, which would join the
/// sentence's last word to the question's first. The quotes keep them apart.
String aiAskModeQuery({
  required String sentencePlain,
  required String promptBody,
}) {
  String flat(String s) => s.replaceAll(RegExp(r'\s+'), ' ').trim();
  final sentence = flat(sentencePlain);
  final prompt = flat(promptBody);
  if (sentence.isEmpty) return prompt;
  return '"$sentence" $prompt';
}

/// Null when the question is empty or too long for an address.
Uri? aiAskModeUri({
  required String sentencePlain,
  required String promptBody,
}) {
  if (promptBody.trim().isEmpty) return null;
  final uri = Uri.parse(kAiAskModeUrl).replace(queryParameters: {
    'udm': '50',
    'q': aiAskModeQuery(sentencePlain: sentencePlain, promptBody: promptBody),
  });
  return uri.toString().length > kAiAskModeMaxUrl ? null : uri;
}

class AiAskPrompt {
  const AiAskPrompt({
    required this.id,
    required this.body,
    required this.createdAt,
  });

  final String id;
  final String body;
  final String createdAt;

  Map<String, dynamic> toJson() => {
        'id': id,
        'body': body,
        'created_at': createdAt,
      };

  static AiAskPrompt? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final id = '${raw['id'] ?? ''}'.trim();
    final body = '${raw['body'] ?? ''}'.trim();
    final at = '${raw['created_at'] ?? ''}'.trim();
    if (id.isEmpty || body.isEmpty) return null;
    return AiAskPrompt(
      id: id,
      body: body,
      createdAt: at.isEmpty ? DateTime.now().toUtc().toIso8601String() : at,
    );
  }

  AiAskPrompt copyWith({String? body}) {
    return AiAskPrompt(
      id: id,
      body: body ?? this.body,
      createdAt: createdAt,
    );
  }
}

String newAiAskPromptId() =>
    'p_${DateTime.now().toUtc().microsecondsSinceEpoch}';

/// Clipboard payload: sentence, two blank lines, then prompt (182 J9).
String buildAiAskClipboard({
  required String sentencePlain,
  required String promptBody,
}) {
  return '${sentencePlain.trim()}\n\n\n${promptBody.trim()}';
}
