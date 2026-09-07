/// Persist AI-ask prompts locally (design/182).
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'ai_ask_prompt_models.dart';

abstract class AiAskPromptStore {
  Future<List<AiAskPrompt>> load();

  Future<void> save(List<AiAskPrompt> prompts);

  Future<bool> isSeeded();

  Future<void> setSeeded(bool value);
}

class PrefsAiAskPromptStore implements AiAskPromptStore {
  PrefsAiAskPromptStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<List<AiAskPrompt>> load() async {
    final p = await _ready();
    final raw = p.getString(kAiAskPromptsPrefsKey);
    if (raw == null || raw.trim().isEmpty) return const [];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];
      final out = <AiAskPrompt>[];
      for (final item in decoded) {
        final prompt = AiAskPrompt.fromJson(item);
        if (prompt != null) out.add(prompt);
      }
      return out;
    } catch (_) {
      return const [];
    }
  }

  @override
  Future<void> save(List<AiAskPrompt> prompts) async {
    final p = await _ready();
    final encoded = jsonEncode(prompts.map((e) => e.toJson()).toList());
    await p.setString(kAiAskPromptsPrefsKey, encoded);
  }

  @override
  Future<bool> isSeeded() async {
    final p = await _ready();
    return p.getBool(kAiAskSeededPrefsKey) ?? false;
  }

  @override
  Future<void> setSeeded(bool value) async {
    final p = await _ready();
    await p.setBool(kAiAskSeededPrefsKey, value);
  }
}

class MemoryAiAskPromptStore implements AiAskPromptStore {
  List<AiAskPrompt> _prompts = [];
  bool _seeded = false;

  @override
  Future<List<AiAskPrompt>> load() async => List.unmodifiable(_prompts);

  @override
  Future<void> save(List<AiAskPrompt> prompts) async {
    _prompts = List.of(prompts);
  }

  @override
  Future<bool> isSeeded() async => _seeded;

  @override
  Future<void> setSeeded(bool value) async {
    _seeded = value;
  }
}

/// Load prompts; seed example once when empty and never seeded (182 J8).
Future<List<AiAskPrompt>> loadAiAskPromptsEnsuringSeed(
  AiAskPromptStore store,
) async {
  final seeded = await store.isSeeded();
  final list = await store.load();
  if (list.isEmpty && !seeded) {
    final seed = AiAskPrompt(
      id: newAiAskPromptId(),
      body: kAiAskSeedPromptBody,
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
    await store.save([seed]);
    await store.setSeeded(true);
    return [seed];
  }
  return list;
}
