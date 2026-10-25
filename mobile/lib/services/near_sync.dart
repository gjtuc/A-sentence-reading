/// design/410 — phone <-> web sync over one ordered byte pipe.
///
/// Both sides run the same steps:
///   1. send `inv` (papers held + reading spots),
///   2. ask with `want` for the papers the other side lacks,
///   3. send the asked papers (`paper` header, then byte frames), then for every
///      paper both sides will hold the user files the other lacks (`extra`, same
///      framing: shadowing takes, chunk plan, voice), then `sent`,
///   4. after storing everything received, send `fin`.
/// Done when both `fin` are exchanged.
///
/// design/450 — `inv` also carries `gone` (paper id -> ms the user deleted it)
/// and each paper's `added` (ms it reached that device, 0 when older than this
/// field). A paper is dropped here when the other side deleted it at or after it
/// arrived here, and never asked for when this side deleted it at or after it
/// arrived there. A later import is newer than the delete, so it spreads again.
/// Papers the user hid but may still bring back are neither offered nor taken.
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
  const NearPaper({
    required this.id,
    required this.title,
    this.hash = '',
    this.added = 0,
  });

  factory NearPaper.fromJson(Map<String, dynamic> json) => NearPaper(
        id: '${json['id'] ?? ''}'.trim(),
        title: '${json['title'] ?? ''}'.trim(),
        hash: '${json['hash'] ?? ''}'.trim(),
        added: _asMs(json['added']),
      );

  final String id;
  final String title;
  final String hash;

  /// Ms this device got the paper; 0 when it predates design/450.
  final int added;

  Map<String, Object?> toJson() =>
      {'id': id, 'title': title, 'hash': hash, 'added': added};
}

int _asMs(Object? v) {
  if (v is int) return v < 0 ? 0 : v;
  if (v is num) return v < 0 ? 0 : v.toInt();
  return 0;
}

Map<String, int> nearGoneFromJson(Object? raw) {
  final out = <String, int>{};
  if (raw is! Map) return out;
  for (final e in raw.entries) {
    final id = '${e.key}'.trim();
    final at = _asMs(e.value);
    if (id.isNotEmpty && at > 0) out[id] = at;
  }
  return out;
}

/// design/450 — a device that remembers which papers the user deleted.
abstract class NearForget {
  /// Paper id -> ms the user deleted it here, or learned it was deleted.
  Future<Map<String, int>> gone();

  /// Ids hidden here that the user can still bring back.
  Future<Set<String>> hidden();

  /// Remember [gone] (newest per id) and delete the [drop] ids held here.
  Future<void> forget(Map<String, int> gone, List<String> drop);
}

/// What one device holds and how it stores what arrives.
abstract class NearLocal {
  Future<List<NearPaper>> papers();
  Future<Map<String, Uint8List>> pack(String id);
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files);
  Future<Map<String, Map<String, dynamic>>> progress();
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> rows);

  /// Per paper id, the names of user files held (e.g. voice files).
  Future<Map<String, List<String>>> extraNames();

  /// User files of one paper, leaving out the names the other side holds.
  Future<Map<String, Uint8List>> extraPack(String id, Set<String> skipNames);

  /// Fold the other side's user files of one paper in; returns files changed.
  Future<int> mergeExtra(String id, Map<String, Uint8List> files);
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
    this.extraBytesIn = 0,
    this.extraBytesOut = 0,
  });

  final int wantIn;
  final int gotIn;
  final int wantOut;
  final int sentOut;

  /// All bytes moved, papers and user files together.
  final int bytesIn;
  final int bytesOut;

  /// The part of [bytesIn] / [bytesOut] that is user files (`extra`).
  final int extraBytesIn;
  final int extraBytesOut;
}

class NearSyncReport {
  const NearSyncReport({
    required this.papersIn,
    required this.papersOut,
    required this.progressRows,
    required this.failed,
    this.extrasIn = 0,
    this.extrasOut = 0,
    this.papersGone = 0,
    this.times = const {},
  });

  final int papersIn;
  final int papersOut;
  final int progressRows;
  final List<String> failed;

  /// Papers deleted here because the other side deleted them (design/450).
  final int papersGone;

  /// User files changed here / papers whose user files were sent.
  final int extrasIn;
  final int extrasOut;

  /// Milliseconds spent: `pack_ms`, `send_ms` (awaiting the pipe), `room_ms`
  /// (waiting for acks), `store_ms`, `sync_ms` (whole run).
  final Map<String, int> times;
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
  _Incoming(this.paper, this.rels, this.sizes, {this.extra = false});

  final NearPaper paper;
  final bool extra;
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

  NearForget? get _forget {
    final l = local;
    return l is NearForget ? l as NearForget : null;
  }

  Set<String> _mine = {};
  final _myAdded = <String, int>{};
  Map<String, int> _myGone = {};
  Set<String> _hidden = {};
  var _papersGone = 0;
  final _peerIds = <String>{};
  final _peerExtras = <String, Set<String>>{};
  var _extrasIn = 0;
  var _extrasOut = 0;
  final _clock = Stopwatch();
  final _packWatch = Stopwatch();
  final _sendWatch = Stopwatch();
  final _roomWatch = Stopwatch();
  final _storeWatch = Stopwatch();
  var _wantIn = 0;
  var _gotIn = 0;
  var _wantOut = 0;
  var _sentOut = 0;
  var _missingOut = 0;
  var _bytesIn = 0;
  var _bytesOut = 0;
  var _extraBytesIn = 0;
  var _extraBytesOut = 0;
  final _reportWatch = Stopwatch();
  var _ackedOut = 0;
  var _ackedIn = 0;
  var _progressRows = 0;
  final _failed = <String>[];
  _Incoming? _incoming;
  var _peerSent = false;
  var _finSent = false;
  var _peerFin = false;

  Future<NearSyncReport> run() async {
    _clock.start();
    _sub = pipe.frames.listen(
      _onFrame,
      onError: (Object _) => _fail('pipe_error'),
      onDone: () => _fail('closed'),
    );
    _poke();
    try {
      final papers = await local.papers();
      _mine = {for (final p in papers) p.id};
      for (final p in papers) {
        _myAdded[p.id] = p.added;
      }
      final forget = _forget;
      if (forget != null) {
        _myGone = await forget.gone();
        _hidden = await forget.hidden();
      }
      final rows = await local.progress();
      final extras = await local.extraNames();
      await _send({
        't': 'inv',
        'papers': [
          for (final p in papers)
            if (!_hidden.contains(p.id)) p.toJson(),
        ],
        'progress': rows,
        'extras': extras,
        'gone': _myGone,
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
      extraBytesIn: _extraBytesIn,
      extraBytesOut: _extraBytesOut,
    ));
    _reportWatch
      ..reset()
      ..start();
  }

  /// [_report] at most every 250 ms while bytes stream.
  void _reportSoon() {
    if (_reportWatch.isRunning && _reportWatch.elapsedMilliseconds < 250) return;
    _report();
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
      case 'extra':
        _onPaperHeader(m, extra: true);
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
    final theirGone = nearGoneFromJson(m['gone']);
    bool goneSince(Map<String, int> gone, String id, int added) {
      final at = gone[id];
      return at != null && at >= added;
    }

    final drop = [
      for (final id in _mine)
        if (goneSince(theirGone, id, _myAdded[id] ?? 0)) id,
    ]..sort();
    _mine.removeAll(drop);
    final want = [
      for (final p in theirs)
        if (p.id.isNotEmpty &&
            !_mine.contains(p.id) &&
            !_hidden.contains(p.id) &&
            !goneSince(_myGone, p.id, p.added) &&
            !goneSince(theirGone, p.id, p.added))
          p.id,
    ];
    _peerIds.addAll([
      for (final p in theirs)
        if (!goneSince(_myGone, p.id, p.added)) p.id,
    ]);
    final forget = _forget;
    if (forget != null && (drop.isNotEmpty || theirGone.isNotEmpty)) {
      _storeTurn = _storeTurn.then((_) async {
        try {
          await forget.forget(theirGone, drop);
          _papersGone = drop.length;
        } catch (_) {}
      });
    }
    if (m['extras'] is Map) {
      for (final e in (m['extras'] as Map).entries) {
        if (e.value is List) {
          _peerExtras['${e.key}'] = {for (final v in e.value as List) '$v'};
        }
      }
    }
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

  void _onPaperHeader(Map<String, dynamic> m, {bool extra = false}) {
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
    final inc = _Incoming(paper, rels, sizes, extra: extra)..skipEmpty();
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
    if (inc.extra) _extraBytesIn += data.length;
    _reportSoon();
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
      _storeWatch.start();
      try {
        if (inc.extra) {
          try {
            _extrasIn += await local.mergeExtra(inc.paper.id, inc.files);
          } catch (_) {}
          return;
        }
        var ok = false;
        try {
          ok = await local.store(inc.paper, inc.files);
        } catch (_) {
          ok = false;
        }
        if (!ok) _failed.add(inc.paper.id);
        _gotIn += 1;
        _report();
      } finally {
        _storeWatch.stop();
      }
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
    if (_bytesOut - _ackedOut > kNearWindow) _roomWatch.start();
    while (!_done.isCompleted && _bytesOut - _ackedOut > kNearWindow) {
      _room ??= Completer<void>();
      await _room!.future;
    }
    _roomWatch.stop();
    if (_done.isCompleted) throw const NearSyncError('stopped');
  }

  Future<void> _sendPapers(List<String> ids) async {
    _wantOut = ids.length;
    _report();
    try {
      for (final id in ids) {
        _packWatch.start();
        final files = _mine.contains(id)
            ? await local.pack(id)
            : const <String, Uint8List>{};
        _packWatch.stop();
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
          await _sendFiles(entries);
        }
        _sentOut += 1;
        _report();
      }
      final together = {..._mine.intersection(_peerIds), ...ids.where(_mine.contains)};
      for (final id in together.toList()..sort()) {
        _packWatch.start();
        final files = await local.extraPack(id, _peerExtras[id] ?? const {});
        _packWatch.stop();
        final entries = files.entries
            .where((e) => nearSafeRel(e.key))
            .toList(growable: false);
        if (entries.isEmpty) continue;
        await _send({
          't': 'extra',
          'id': id,
          'files': [
            for (final e in entries) {'rel': e.key, 'size': e.value.length},
          ],
        });
        await _sendFiles(entries, extra: true);
        _extrasOut += 1;
      }
      _report();
      await _send({'t': 'sent'});
    } on NearSyncError catch (e) {
      _fail(e.code);
    } catch (_) {
      _fail('send_failed');
    }
  }

  Future<void> _sendFiles(
    List<MapEntry<String, Uint8List>> entries, {
    bool extra = false,
  }) async {
    for (final e in entries) {
      final bytes = e.value;
      for (var at = 0; at < bytes.length; at += kNearChunk) {
        await _waitRoom();
        final end =
            (at + kNearChunk < bytes.length) ? at + kNearChunk : bytes.length;
        _sendWatch.start();
        await pipe.send(nearBytesFrame(bytes, at, end));
        _sendWatch.stop();
        _bytesOut += end - at;
        if (extra) _extraBytesOut += end - at;
        _reportSoon();
      }
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
    _report();
    _done.complete(NearSyncReport(
      papersIn: _gotIn - _failed.length,
      papersOut: _sentOut - _missingOut,
      progressRows: _progressRows,
      failed: List.unmodifiable(_failed),
      extrasIn: _extrasIn,
      extrasOut: _extrasOut,
      papersGone: _papersGone,
      times: {
        'pack_ms': _packWatch.elapsedMilliseconds,
        'send_ms': _sendWatch.elapsedMilliseconds,
        'room_ms': _roomWatch.elapsedMilliseconds,
        'store_ms': _storeWatch.elapsedMilliseconds,
        'sync_ms': _clock.elapsedMilliseconds,
      },
    ));
  }
}
