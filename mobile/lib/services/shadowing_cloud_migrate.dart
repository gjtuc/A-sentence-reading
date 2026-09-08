/// design/187 — one-shot pull shadowing takes/voice to device, then wipe GCS.
library;

import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import 'evidence_bus.dart';
import 'shadowing_disk_store.dart';

String shadowingCloudMigratedPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return 'asr.shadowing.cloud_migrated.v1';
  final safe = u.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');
  return 'asr.shadowing.cloud_migrated.v1.u.$safe';
}

/// Pull takes (+ voice blobs) for [cacheIds], then ACK wipe of shadowing/voice.
Future<bool> migrateShadowingCloudOnce({
  required AsrClient client,
  required String? uid,
  required List<String> cacheIds,
  ShadowingDiskStore? disk,
}) async {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return false;
  final prefs = await SharedPreferences.getInstance();
  final key = shadowingCloudMigratedPrefsKey(u);
  if (prefs.getBool(key) == true) return true;

  final store = disk ?? ShadowingDiskStore();
  store.bindUid(u);

  asrEvidenceBus?.record(
    'shadowing_local_migrate_start',
    severity: 'lifecycle',
    ok: true,
    details: {'paper_n': cacheIds.length},
  );

  for (final rawId in cacheIds) {
    final cacheId = rawId.trim();
    if (cacheId.isEmpty) continue;
    try {
      final remote = await client.fetchShadowingTakes(cacheId);
      Map<String, dynamic>? takes;
      if (remote['takes'] is Map) {
        takes = Map<String, dynamic>.from(remote['takes'] as Map);
      } else if (remote['sentences'] is Map) {
        takes = Map<String, dynamic>.from(remote);
      }
      if (takes == null) continue;
      await store.writeTakesJson(cacheId, takes);
      final sentences = takes['sentences'];
      if (sentences is! Map) continue;
      for (final sent in sentences.values) {
        if (sent is! Map) continue;
        final chunks = sent['chunks'];
        if (chunks is! List) continue;
        for (final c in chunks) {
          if (c is! Map) continue;
          final bk = '${c['blob_key'] ?? ''}'.trim();
          if (bk.isEmpty) continue;
          final bytes = await client.fetchVoiceBlob(bk);
          if (bytes != null && bytes.isNotEmpty) {
            await store.writeVoiceBytes(cacheId, bk, bytes);
          }
        }
      }
    } catch (_) {
      // EDGE: continue other papers; ACK only if we attempt wipe after pulls.
    }
  }

  final acked = await client.ackShadowingLocalMigrate();
  if (acked) {
    await prefs.setBool(key, true);
  }
  asrEvidenceBus?.record(
    'shadowing_local_migrate_done',
    severity: 'lifecycle',
    ok: acked,
    details: {'paper_n': cacheIds.length, 'wiped': acked ? 1 : 0},
  );
  return acked;
}
