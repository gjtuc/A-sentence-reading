/// design/364 — write the sample row onto disk so 보관함 shows it with no server.
library;

import '../api/shadowing_chunk_plan.dart';
import '../services/paper_disk_store.dart';
import '../services/shadowing_disk_store.dart';
import 'sample_corpus.dart';

/// Bump when [sampleAllLines] changes, so an old seed gets rewritten.
const int kSampleSeedVersion = 1;

bool isSampleCacheId(String? id) => (id ?? '').trim() == kSampleCacheId;

String sampleSentenceId(SampleLine line) => 'sent_${line.id}';

/// Reader/practice session for the sample row.
///
/// `section` is never `title`: the title aligner rewrites those rows, which
/// would break the one-to-one match with the chunk plan.
Map<String, dynamic> sampleSessionJson() => {
      'session_id': 'ses_$kSampleCacheId',
      'cache_id': kSampleCacheId,
      'title': kSampleTitle,
      'sample_seed_version': kSampleSeedVersion,
      'sentences': [
        for (final line in kSampleFixedLines)
          {
            'id': sampleSentenceId(line),
            'text': line.text,
            'section': '고정 문장',
          },
        for (final line in kSampleFreshLines)
          {
            'id': sampleSentenceId(line),
            'text': line.text,
            'section': '새 문장',
          },
      ],
      'figures': const <Map<String, dynamic>>[],
    };

Map<String, dynamic> sampleChunkPlan() => {
      'status': 'ok',
      'sentences': {
        for (final line in sampleAllLines)
          sampleSentenceId(line): {
            'text': line.text,
            'chunks': line.chunks,
          },
      },
    };

PaperDiskIndexEntry sampleIndexEntry() => PaperDiskIndexEntry(
      id: kSampleCacheId,
      title: kSampleTitle,
      source: 'sample',
      updatedAt: '',
      sentenceCount: sampleAllLines.length,
      figureCount: 0,
      pipelineVersion: 'sample-v$kSampleSeedVersion',
    );

/// True when this call wrote the row.
///
/// The session and the plan live in two stores that are wiped separately, so a
/// present session is not proof the plan survived.
Future<bool> ensureSampleRow({
  required PaperDiskStore paperDisk,
  required ShadowingDiskStore shadowDisk,
}) async {
  if (!paperDisk.isBound || !shadowDisk.isBound) return false;
  if (!await sampleRowNeedsWrite(
    paperDisk: paperDisk,
    shadowDisk: shadowDisk,
  )) {
    return false;
  }
  final wrote = await paperDisk.writeSessionJson(
    kSampleCacheId,
    sampleSessionJson(),
  );
  if (!wrote) return false;
  final planned = await shadowDisk.writeChunkPlanJson(
    kSampleCacheId,
    sampleChunkPlan(),
  );
  if (!planned) return false;
  await paperDisk.upsertIndex(sampleIndexEntry(), caller: 'sample_seed');
  return true;
}

Future<bool> sampleRowNeedsWrite({
  required PaperDiskStore paperDisk,
  required ShadowingDiskStore shadowDisk,
}) async {
  final session = await paperDisk.loadSessionJson(kSampleCacheId);
  final seeded = (session?['sample_seed_version'] as num?)?.toInt() ?? 0;
  if (seeded != kSampleSeedVersion) return true;
  final sentences = session?['sentences'];
  if (sentences is! List || sentences.length != sampleAllLines.length) {
    return true;
  }
  final plan = await shadowDisk.loadChunkPlanJson(kSampleCacheId);
  if (!shadowingPlanStatusIsOk(plan)) return true;
  return countShadowingReadySentences(plan) < sampleAllLines.length;
}
