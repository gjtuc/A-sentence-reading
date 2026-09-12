/// design/250 — thin hooks to avoid skill_store ↔ practice_cloud_sync cycles.
library;

typedef PracticeStorePush = void Function(Map<String, dynamic> store);
typedef PracticeEnsurePulled = Future<void> Function({bool force});

PracticeStorePush? asrSchedulePushFocus;
PracticeStorePush? asrSchedulePushSkill;
PracticeEnsurePulled? asrPracticeEnsurePulled;
