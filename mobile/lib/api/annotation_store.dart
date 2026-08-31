/// Local uid-scoped annotation store (GCS sync cache).
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'annotation_models.dart';

Future<AnnotationsStore> loadAnnotationsStore({required String? uid}) async {
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(annotationsPrefsKey(uid));
  if (raw == null || raw.isEmpty) return AnnotationsStore.empty();
  try {
    return AnnotationsStore.fromJson(jsonDecode(raw));
  } catch (_) {
    return AnnotationsStore.empty();
  }
}

Future<void> saveAnnotationsStore({
  required String? uid,
  required AnnotationsStore store,
}) async {
  final p = await SharedPreferences.getInstance();
  final compact = compactAnnotationsStore(store);
  await p.setString(annotationsPrefsKey(uid), jsonEncode(compact.toJson()));
}

Future<void> purgePaperAnnotations({
  required String? uid,
  required String cacheId,
}) async {
  final store = await loadAnnotationsStore(uid: uid);
  final pk = annotationPaperKey(cacheId);
  final papers = Map<String, PaperAnnotations>.from(store.papers);
  papers.remove(pk);
  await saveAnnotationsStore(uid: uid, store: AnnotationsStore(papers: papers));
}
