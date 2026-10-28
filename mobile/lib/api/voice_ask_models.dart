/// design/475 — a spoken AI question: what is sent, and how the screen reads.
library;

/// Sent between the sentence and a question that came from the microphone.
const String kVoiceAskHint =
    '이 질문은 음성 인식으로 받아 적어서 틀린 글자가 있을 수 있어요. 소리가 비슷한 말로 이해해 주세요.';

/// A take stops on its own after this; nothing else ends it but a tap.
const Duration kVoiceAskMax = Duration(minutes: 3);

/// What the server wrote down. [error] is empty when it worked; [text] can
/// still be empty when nothing was said.
class VoiceAskHeard {
  const VoiceAskHeard(this.text, {this.error = ''});

  final String text;
  final String error;

  bool get ok => error.isEmpty;
}

/// The question as sent: a spoken one carries [kVoiceAskHint] on its own line.
String voiceAskPrompt(String question, {required bool spoken}) =>
    spoken ? '$kVoiceAskHint\n$question' : question;

/// `0:07`, `2:41`.
String voiceAskClock(Duration d) {
  final s = d.inSeconds.clamp(0, 5999);
  return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
}

String voiceAskErrorKo(String error) => switch (error) {
      'auth_required' => '음성 질문은 로그인한 뒤 쓸 수 있어요.',
      'access_denied' => '음성 질문은 이용 권한이 있어야 쓸 수 있어요.',
      'audio_too_large' => '녹음이 너무 길어요. 조금 짧게 말해 주세요.',
      'offline' => '인터넷에 연결되지 않아 글자로 바꾸지 못했어요.',
      _ => '글자로 바꾸지 못했어요. 다시 해 볼까요?',
    };

/// The glow follows the voice: it rises quickly and settles slowly, so a word
/// lights it and the pause after does not snap it dark.
double voiceGlowStep(double shown, double heard) {
  final k = heard > shown ? 0.45 : 0.08;
  return shown + (heard - shown) * k;
}
