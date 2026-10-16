/// design/410 — phone <-> web sync over one ordered byte pipe.
///
/// Both sides run the same steps:
///   1. send `inv` (papers held + reading spots),
///   2. ask with `want` for the papers the other side lacks,
///   3. send the asked papers (`paper` header, then byte frames), then `sent`,
///   4. after storing everything received, send `fin`.
/// Done when both `fin` are exchanged. Nothing is ever deleted.
///
/// Every frame is binary with a one-byte kind, because a browser data channel may
/// reorder text frames against binary ones.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

const int kNearChunk = 16 * 1024;
const int kNearWindow = 2 * 1024 * 1024;
const int kNearAckEvery = 256 * 1024;
const Duration kNearQuiet = Duration(seconds: 45);

const int _kJson = 1;
const int _kBytes = 2;

/// One ordered, reliable pipe (a WebRTC data channel, or memory in tests).
abstract class NearPipe {
  Stream<Uint8List> get frames;
  Future<void> send(Uint8List frame);
}

class NearPaper {
  const NearPaper({required this.id, required this.title, this.hash = ''});

  factory NearPaper.fromJson(Map<String, dynamic> json) => NearPaper(
        id: '${json['id'] ?? ''}'.trim(),
        title: '${json['title'] ?? ''}'.trim(),
        hash: '${json['hash'] ?? ''}'.trim(),
      );

  final String id;
  final String title;
  final String hash;

  Map<String, Object?> toJson() => {'id': id, 'title': title, 'hash': hash};
}

/// What one device holds and how it stores what arrives.
abstract class NearLocal {
  Future<List<NearPaper>> papers();
  Future<Map<String, Uint8List>> pack(String id);
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files);
  Future<Map<String, Map<String, dynamic>>> progress();
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> rows);
}

class NearSyncError implements Exception {
  const NearSyncError(this.code);
  final String code;

  @override
  String toString() => 'NearSyncError($code)';
}

class NearSyncProgress {
  const NearSyncProgress({
    this.wantIn = 0,
    this.gotIn = 0,
    this.wantOut = 0,
    this.sentOut = 0,
    this.bytesIn = 0,
    this.bytesOut = 0,
  });

  final int wantIn;
  final int gotIn;
  final int wantOut;
  final int sentOut;
  final int bytesIn;
  final int bytesOut;
}

class NearSyncReport {
  const NearSyncReport({
    required this.papersIn,
    required this.papersOut,
    required this.progressRows,
    required this.failed,
  });

  final int papersIn;
  final int papersOut;
  final int progressRows;
  final List<String> failed;
}

Uint8List nearJsonFrame(Map<String, Object?> message) {
  final body = utf8.encode(jsonEncode(message));
  final out = Uint8List(body.length + 1);
  out[0] = _kJson;
  out.setRange(1, out.length, body);
  return out;
}

Uint8List nearBytesFrame(Uint8List data, int start, int end) {
  final out = Uint8List(end - start + 1);
  out[0] = _kBytes;
  out.setRange(1, out.length, data, start);
  return out;
}

bool nearSafeRel(String rel) {
  if (rel.isEmpty || rel.length > 200) return false;
  if (rel.startsWith('/') || rel.contains('\\') || rel.contains(':')) return false;
  return !rel.split('/').any((s) => s.isEmpty || s == '.' || s == '..');
}

class _Incoming {
  _Incoming(this.paper, this.rels, this.sizes);

  final NearPaper paper;
  final List<String> rels;
  final List<int> sizes;
  final Map<String, Uint8List> files = {};
  var index = 0;
  var buffer = BytesBuilder(copy: false);

  bool get complete => index >= rels.length;

  void skipEmpty() {
    while (!complete && sizes[index] == 0) {
      files[rels[index]] = Uint8List(0);
      index += 1;
    }
  }
}

class NearSync {
  NearSync(this.pipe, this.local, {this.onProgress, this.quiet = kNearQuiet});

  final NearPipe pipe;
  final NearLocal local;
  final void Function(NearSyncProgress progress)? onProgress;
  final Duration quiet;

  final _done = Completer<NearSyncReport>();
  StreamSubscription<Uint8List>? _sub;
  Timer? _watch;
  Future<void> _storeTurn = Future.value();
  Completer<void>? _room;

  Set<String> _mine = {};
  var _wantIn = 0;
  var _gotIn = 0;
  var _wantOut = 0;
  var _sentOut = 0;
  var _missingOut = 0;
  var _bytesIn = 0;
  var _bytesOut = 0;
  var _ackedOut = 0;
  var _ackedIn = 0;
  var _progressRows = 0;
  final _failed = <String>[];
  _Incoming? _incoming;
  var _peerSent = false;
  var _finSent = false;
  var _peerFin = false;

  Future<NearSyncReport> run() async {
    _sub = pipe.frames.listen(
      _onFrame,
      onError: (Object _) => _fail('pipe_error'),
      onDone: () => _fail('closed'),
    );
    _poke();
    try {
      final papers = await local.papers();
      _mine = {for (final p in papers) p.id};
      final rows = await local.progress();
      await _send({
        't': 'inv',
        'papers': [for (final p in papers) p.toJson()],
        'progress': rows,
      });
    } catch (e) {
      _fail('inv_failed');
    }
    try {
      return await _done.future;
    } finally {
      _watch?.cancel();
      await _sub?.cancel();
    }
  }

  void _poke() {
    _watch?.cancel();
    _watch = Timer(quiet, () => _fail('quiet'));
  }

  void _fail(String code) {
    if (_done.isCompleted) return;
    _room?.complete();
    _done.completeError(NearSyncError(code));
  }

  void _report() {
    onProgress?.call(NearSyncProgress(
      wantIn: _wantIn,
      gotIn: _gotIn,
      wantOut: _wantOut,
      sentOut: _sentOut,
      bytesIn: _bytesIn,
      bytesOut: _bytesOut,
    ));
  }

  Future<void> _send(Map<String, Object?> message) =>
      pipe.send(nearJsonFrame(message));

  void _onFrame(Uint8List frame) {
    if (_done.isCompleted) return;
    _poke();
    try {
      if (frame.isEmpty) throw const NearSyncError('empty_frame');
      if (frame[0] == _kBytes) {
        _onBytes(Uint8List.sublistView(frame, 1));
      } else if (frame[0] == _kJson) {
        final m = jsonDecode(utf8.decode(Uint8List.sublistView(frame, 1)));
        if (m is! Map) throw const NearSyncError('bad_message');
        _onMessage(Map<String, dynamic>.from(m));
      } else {
        throw const NearSyncError('bad_frame');
      }
    } on NearSyncError catch (e) {
      _fail(e.code);
    } catch (_) {
      _fail('bad_message');
    }
  }

  void _onMessage(Map<String, dynamic> m) {
    switch (m['t']) {
      case 'inv':
        _onInventory(m);
      case 'want':
        final ids = (m['ids'] is List)
            ? [for (final v in m['ids'] as List) '$v'.trim()]
            : const <String>[];
        unawaited(_sendPapers(ids));
      case 'paper':
        _onPaperHeader(m);
      case 'ack':
        final n = m['n'];
        if (n is int && n > _ackedOut) _ackedOut = n;
        _wake();
      case 'sent':
        _peerSent = true;
        _storeTurn = _storeTurn.then((_) => _maybeFin());
      case 'fin':
        _peerFin = true;
        _maybeDone();
      default:
        throw const NearSyncError('bad_message');
    }
  }

  void _onInventory(Map<String, dynamic> m) {
    final theirs = <NearPaper>[
      if (m['papers'] is List)
        for (final raw in m['papers'] as List)
          if (raw is Map) NearPaper.fromJson(Map<String, dynamic>.from(raw)),
    ];
    final want = [
      for (final p in theirs)
        if (p.id.isNotEmpty && !_mine.contains(p.id)) p.id,
    ];
    _wantIn = want.length;
    final rows = <String, Map<String, dynamic>>{};
    if (m['progress'] is Map) {
      for (final e in (m['progress'] as Map).entries) {
        if (e.value is Map) {
          rows['${e.key}'] = Map<String, dynamic>.from(e.value as Map);
        }
      }
    }
    _storeTurn = _storeTurn.then((_) async {
      _progressRows = await local.mergeProgress(rows);
    }).catchError((Object _) => _fail('progress_failed'));
    _report();
    unawaited(_send({'t': 'want', 'ids': want}).catchError((Object _) {
      _fail('send_failed');
    }));
  }

  void _onPaperHeader(Map<String, dynamic> m) {
    if (_incoming != null) throw const NearSyncError('paper_overlap');
    final paper = NearPaper.fromJson(m);
    if (paper.id.isEmpty) throw const NearSyncError('bad_paper');
    if (m['missing'] == true) {
      _gotIn += 1;
      _failed.add(paper.id);
      _report();
      return;
    }
    final rels = <String>[];
    final sizes = <int>[];
    for (final raw in (m['files'] is List) ? m['files'] as List : const []) {
      if (raw is! Map) throw const NearSyncError('bad_paper');
      final rel = '${raw['rel'] ?? ''}';
      final size = raw['size'];
      if (!nearSafeRel(rel) || size is! int || size < 0) {
        throw const NearSyncError('bad_paper');
      }
      rels.add(rel);
      sizes.add(size);
    }
    final inc = _Incoming(paper, rels, sizes)..skipEmpty();
    _incoming = inc;
    if (inc.complete) _finishPaper();
  }

  void _onBytes(Uint8List data) {
    final inc = _incoming;
    if (inc == null || inc.complete) throw const NearSyncError('stray_bytes');
    inc.buffer.add(data);
    final have = inc.buffer.length;
    final size = inc.sizes[inc.index];
    if (have > size) throw const NearSyncError('file_overrun');
    _bytesIn += data.length;
    if (have == size) {
      inc.files[inc.rels[inc.index]] = inc.buffer.takeBytes();
      inc.buffer = BytesBuilder(copy: false);
      inc.index += 1;
      inc.skipEmpty();
    }
    if (inc.complete) {
      _finishPaper();
    } else if (_bytesIn - _ackedIn >= kNearAckEvery) {
      _ack();
    }
  }

  void _ack() {
    _ackedIn = _bytesIn;
    unawaited(_send({'t': 'ack', 'n': _bytesIn}).catchError((Object _) {
      _fail('send_failed');
    }));
  }

  void _finishPaper() {
    final inc = _incoming!;
    _incoming = null;
    _ack();
    _storeTurn = _storeTurn.then((_) async {
      var ok = false;
      try {
        ok = await local.store(inc.paper, inc.files);
      } catch (_) {
        ok = false;
      }
      if (!ok) _failed.add(inc.paper.id);
      _gotIn += 1;
      _report();
    });
  }

  void _wake() {
    final room = _room;
    if (room != null && _bytesOut - _ackedOut <= kNearWindow) {
      _room = null;
      room.complete();
    }
  }

  Future<void> _waitRoom() async {
    while (!_done.isCompleted && _bytesOut - _ackedOut > kNearWindow) {
      _room ??= Completer<void>();
      await _room!.future;
    }
    if (_done.isCompleted) throw const NearSyncError('stopped');
  }

  Future<void> _sendPapers(List<String> ids) async {
    _wantOut = ids.length;
    _report();
    try {
      for (final id in ids) {
        final files = _mine.contains(id)
            ? await local.pack(id)
            : const <String, Uint8List>{};
        final entries = files.entries
            .where((e) => nearSafeRel(e.key))
            .toList(growable: false);
        if (!entries.any((e) => e.key == 'session.json')) {
          await _send({'t': 'paper', 'id': id, 'missing': true});
          _missingOut += 1;
        } else {
          final papers = await local.papers();
          final meta = papers.firstWhere(
            (p) => p.id == id,
            orElse: () => NearPaper(id: id, title: ''),
          );
          await _send({
            't': 'paper',
            ...meta.toJson(),
            'files': [
              for (final e in entries) {'rel': e.key, 'size': e.value.length},
            ],
          });
          for (final e in entries) {
            final bytes = e.value;
            for (var at = 0; at < bytes.length; at += kNearChunk) {
              await _waitRoom();
              final end = (at + kNearChunk < bytes.length)
                  ? at + kNearChunk
                  : bytes.length;
              await pipe.send(nearBytesFrame(bytes, at, end));
              _bytesOut += end - at;
            }
          }
        }
        _sentOut += 1;
        _report();
      }
      await _send({'t': 'sent'});
    } on NearSyncError catch (e) {
      _fail(e.code);
    } catch (_) {
      _fail('send_failed');
    }
  }

  Future<void> _maybeFin() async {
    if (!_peerSent || _finSent || _incoming != null) return;
    _finSent = true;
    try {
      await _send({'t': 'fin'});
    } catch (_) {
      _fail('send_failed');
      return;
    }
    _maybeDone();
  }

  void _maybeDone() {
    if (!_finSent || !_peerFin || _done.isCompleted) return;
    _done.complete(NearSyncReport(
      papersIn: _gotIn - _failed.length,
      papersOut: _sentOut - _missingOut,
      progressRows: _progressRows,
      failed: List.unmodifiable(_failed),
    ));
  }
}
