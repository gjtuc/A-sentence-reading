/// design/495 — the web keeps a second copy of its papers in the PC helper
/// (논문 전송 도우미, `scripts/helper_store.py`), and takes back what the
/// browser lost when its data was cleared.
///
/// The helper is a second store, so the same rules as near sync apply
/// (design/450): a paper deleted in one browser goes from the copy and from the
/// other browsers, unless that browser got it again after the delete.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'near_sync.dart';

export 'helper_store_io.dart' if (dart.library.js_interop) 'helper_store_web.dart'
    show
        connectHelperStore,
        connectHelperWatch,
        probeHelperFromPhone,
        askBrowserToKeepStorage,
        markHelperWanted;

const int kHelperStorePort = 47815;

/// design/496 — helpers before this cannot start a sync by themselves.
const int kHelperLatestVersion = 2;

bool helperIsOld(Map<String, Object?>? hello) =>
    hello != null && (int.tryParse('${hello['helper'] ?? ''}') ?? 0) < kHelperLatestVersion;

class HelperWatch {
  HelperWatch({required this.hello, required this.messages, required this.close});
  final Map<String, Object?> hello;

  /// Later messages ({"t":"phone"} when the phone joins); done when the helper goes.
  final Stream<Map<String, Object?>> messages;
  final Future<void> Function() close;
}
const int kHelperProbePort = 47817;
const Duration kHelperOpenLimit = Duration(milliseconds: 1500);

/// One account's folder name in the helper (never the raw uid).
String helperAccountKey(String uid) =>
    sha256.convert(utf8.encode('asr-helper:${uid.trim()}')).toString().substring(0, 32);

class HelperReply {
  const HelperReply(this.json, [this.body]);
  final Map<String, Object?> json;
  final Uint8List? body;
  bool get ok => json['ok'] == true;
}

class HelperStoreError implements Exception {
  const HelperStoreError(this.code);
  final String code;
  @override
  String toString() => 'HelperStoreError($code)';
}

/// The helper's /store socket: JSON text requests, each file body one binary
/// message right after its JSON. Requests run one at a time.
class HelperLine {
  HelperLine({
    required Stream<Object> incoming,
    required void Function(String text) sendText,
    required void Function(Uint8List data) sendBinary,
    required Future<void> Function() close,
  })  : _sendText = sendText,
        _sendBinary = sendBinary,
        _close = close {
    _sub = incoming.listen(
      (m) {
        if (_waiters.isNotEmpty) {
          _waiters.removeAt(0).complete(m);
        } else {
          _queue.add(m);
        }
      },
      onError: (Object _) => _fail(),
      onDone: _fail,
    );
  }

  final void Function(String) _sendText;
  final void Function(Uint8List) _sendBinary;
  final Future<void> Function() _close;
  late final StreamSubscription<Object> _sub;
  final _queue = <Object>[];
  final _waiters = <Completer<Object>>[];
  Future<void> _chain = Future.value();
  bool _closed = false;
  int _q = 0;

  void _fail() {
    _closed = true;
    for (final w in _waiters) {
      if (!w.isCompleted) w.completeError(const HelperStoreError('closed'));
    }
    _waiters.clear();
  }

  Future<Object> _next(Duration limit) {
    if (_queue.isNotEmpty) return Future.value(_queue.removeAt(0));
    if (_closed) return Future.error(const HelperStoreError('closed'));
    final c = Completer<Object>();
    _waiters.add(c);
    return c.future.timeout(limit, onTimeout: () {
      _waiters.remove(c);
      throw const HelperStoreError('timeout');
    });
  }

  /// The helper's first message.
  Future<Map<String, Object?>> hello({Duration limit = kHelperOpenLimit}) async {
    final m = await _next(limit);
    if (m is Map<String, Object?> && m['t'] == 'hello') return m;
    throw const HelperStoreError('no_hello');
  }

  Future<HelperReply> ask(
    Map<String, Object?> req, {
    Uint8List? body,
    bool wantsBody = false,
    Duration limit = const Duration(seconds: 60),
  }) {
    final done = Completer<HelperReply>();
    _chain = _chain.then((_) async {
      try {
        final q = ++_q;
        _sendText(jsonEncode({...req, 'q': q}));
        if (body != null) _sendBinary(body);
        final m = await _next(limit);
        if (m is! Map<String, Object?> || m['q'] != q) {
          throw const HelperStoreError('out_of_step');
        }
        Uint8List? got;
        if (wantsBody && m['ok'] == true) {
          final b = await _next(limit);
          if (b is! Uint8List) throw const HelperStoreError('no_body');
          got = b;
        }
        done.complete(HelperReply(m, got));
      } catch (e) {
        done.completeError(e);
      }
    });
    return done.future;
  }

  Future<void> close() async {
    _closed = true;
    await _sub.cancel();
    await _close();
  }
}

class HelperMirrorReport {
  int sent = 0;
  int restored = 0;
  int droppedHere = 0;
  int droppedThere = 0;
  int failed = 0;
  bool progressMerged = false;

  bool get changedHere => restored > 0 || droppedHere > 0 || progressMerged;

  Map<String, Object?> toJson() => {
        'sent': sent,
        'restored': restored,
        'dropped_here': droppedHere,
        'dropped_there': droppedThere,
        'failed': failed,
        'progress_merged': progressMerged ? 1 : 0,
      };
}

int _ms(Object? v) => v is num && v > 0 ? v.toInt() : 0;

List<String> _names(Object? v) => [
      if (v is List)
        for (final n in v)
          if (n is String && n.isNotEmpty) n,
    ];

/// One pass: deletes both ways, then fill each side with what it lacks, then
/// reading positions.
class HelperMirror {
  HelperMirror({
    required this.line,
    required this.account,
    required this.local,
    required this.forget,
  });

  final HelperLine line;
  final String account;
  final NearLocal local;
  final NearForget forget;

  Future<HelperReply> _ask(Map<String, Object?> req,
          {Uint8List? body, bool wantsBody = false}) =>
      line.ask({...req, 'acct': account}, body: body, wantsBody: wantsBody);

  Future<HelperMirrorReport> run() async {
    final report = HelperMirrorReport();
    final listed = await _ask({'t': 'list'});
    if (!listed.ok) throw HelperStoreError('${listed.json['error'] ?? 'list'}');
    final there = <String, Map<String, Object?>>{};
    final rawPapers = listed.json['papers'];
    if (rawPapers is Map) {
      for (final e in rawPapers.entries) {
        if (e.value is Map) there['${e.key}'] = Map<String, Object?>.from(e.value as Map);
      }
    }
    final thereGone = nearGoneFromJson(listed.json['gone']);
    final mine = {for (final p in await local.papers()) p.id: p};
    final myGone = await forget.gone();
    final hidden = await forget.hidden();

    // Deleted in another browser after this one got it.
    final dropHere = <String, int>{};
    for (final p in mine.values) {
      final at = thereGone[p.id];
      if (at == null || at <= p.added) continue;
      final copy = there[p.id];
      if (copy != null && _ms(copy['saved_at']) > at) continue;
      dropHere[p.id] = at;
    }
    if (dropHere.isNotEmpty) {
      await forget.forget(dropHere, dropHere.keys.toList());
      report.droppedHere = dropHere.length;
      for (final id in dropHere.keys) {
        mine.remove(id);
      }
    }

    // Deleted here: tell the copy (it drops what it saved before the delete).
    final tell = <String, int>{
      for (final e in myGone.entries)
        if (e.value > (thereGone[e.key] ?? 0)) e.key: e.value,
    };
    if (tell.isNotEmpty) {
      final r = await _ask({'t': 'forget', 'gone': tell});
      for (final id in _names(r.json['dropped'])) {
        there.remove(id);
        report.droppedThere += 1;
      }
    }

    for (final p in mine.values) {
      if (hidden.contains(p.id)) continue;
      final copy = there[p.id];
      if (copy != null && _ms(copy['added']) >= p.added) continue;
      try {
        if (await _send(p)) report.sent += 1;
      } catch (e) {
        if (e is HelperStoreError && e.code == 'closed') rethrow;
        report.failed += 1;
      }
    }

    for (final e in there.entries) {
      if (mine.containsKey(e.key) || hidden.contains(e.key)) continue;
      if ((myGone[e.key] ?? 0) >= _ms(e.value['saved_at'])) continue;
      try {
        if (await _restore(e.key, e.value)) report.restored += 1;
      } catch (err) {
        if (err is HelperStoreError && err.code == 'closed') rethrow;
        report.failed += 1;
      }
    }

    final prog = await _ask({'t': 'progress'});
    final rows = prog.json['rows'];
    if (rows is Map && rows.isNotEmpty) {
      final incoming = <String, Map<String, dynamic>>{
        for (final r in rows.entries)
          if (r.value is Map) '${r.key}': Map<String, dynamic>.from(r.value as Map),
      };
      report.progressMerged = await local.mergeProgress(incoming) > 0;
    }
    await _ask({'t': 'put_progress', 'rows': await local.progress()});
    return report;
  }

  Future<bool> _send(NearPaper p) async {
    final files = await local.pack(p.id);
    if (files.isEmpty) return false;
    final extra = await local.extraPack(p.id, const <String>{});
    for (final (kind, set) in [('files', files), ('extra', extra)]) {
      for (final f in set.entries) {
        final r = await _ask(
          {'t': 'put_file', 'id': p.id, 'kind': kind, 'name': f.key},
          body: f.value,
        );
        if (!r.ok) throw HelperStoreError('${r.json['error'] ?? 'put_file'}');
      }
    }
    final done = await _ask({
      't': 'put_done',
      'id': p.id,
      'meta': {
        'title': p.title,
        'hash': p.hash,
        'added': p.added,
        'names': files.keys.toList(),
        'extra': extra.keys.toList(),
      },
    });
    return done.ok;
  }

  Future<bool> _restore(String id, Map<String, Object?> meta) async {
    Future<Map<String, Uint8List>> fetch(String kind, List<String> names) async {
      final out = <String, Uint8List>{};
      for (final n in names) {
        final r = await _ask(
          {'t': 'get_file', 'id': id, 'kind': kind, 'name': n},
          wantsBody: true,
        );
        if (!r.ok || r.body == null) throw HelperStoreError('${r.json['error'] ?? 'get_file'}');
        out[n] = r.body!;
      }
      return out;
    }

    final files = await fetch('files', _names(meta['names']));
    if (files.isEmpty) return false;
    final paper = NearPaper(
      id: id,
      title: '${meta['title'] ?? ''}',
      hash: '${meta['hash'] ?? ''}',
      added: _ms(meta['added']),
    );
    if (!await local.store(paper, files)) return false;
    final extra = await fetch('extra', _names(meta['extra']));
    if (extra.isNotEmpty) await local.mergeExtra(id, extra);
    return true;
  }
}

/// Runs [HelperMirror] a few seconds after the library changes, one pass at a
/// time; a change during a pass runs one more.
class HelperMirrorRunner {
  HelperMirrorRunner({
    required this.pass,
    this.delay = const Duration(seconds: 3),
  });

  final Future<void> Function(String why) pass;
  final Duration delay;
  Timer? _timer;
  bool _running = false;
  String? _again;

  void kick(String why) {
    if (_running) {
      _again = why;
      return;
    }
    _timer?.cancel();
    _timer = Timer(delay, () => unawaited(_go(why)));
  }

  Future<void> _go(String why) async {
    _running = true;
    try {
      await pass(why);
    } catch (_) {
    } finally {
      _running = false;
    }
    final again = _again;
    _again = null;
    if (again != null) kick(again);
  }

  void dispose() => _timer?.cancel();
}
