/// Local AI-ask prompt templates (design/182) — no server sync.
library;

const kAiAskPromptsPrefsKey = 'asr.ai_ask_prompts.v1';
const kAiAskSeededPrefsKey = 'asr.ai_ask_prompts.seeded_v1';

const kAiAskSeedPromptBody = '이 문장에 포함된 단어와 문법을 설명해줘.';

const kAiAskGoogleUrl = 'https://www.google.com/ai';

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
