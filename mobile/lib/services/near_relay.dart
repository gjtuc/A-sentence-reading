/// design/410 — the same near-sync frames through our server, for devices that cannot
/// reach each other (no shared Wi-Fi, company firewall).
///
/// Frames are bundled (`[u32 length][frame]...`) and posted in order as numbered bundles.
/// The other side reads bundle `n`, and asking for `n + 1` deletes `n` on the server.
library;

import 'dart:async';
import 'dart:typed_data';

import 'near_sync.dart';

const int kRelayBundle = 1024 * 1024;
const Duration kRelayLinger = Duration(milliseconds: 150);
const Duration kRelayIdle = Duration(milliseconds: 700);

typedef RelayPut = Future<void> Function(String side, int seq, Uint8List bundle);
typedef RelayTake = Future<Uint8List?> Function(String side, int seq);

Uint8List encodeRelayBundle(List<Uint8List> frames) {
  var size = 0;
  for (final f in frames) {
    size += 4 + f.length;
  }
  final out = Uint8List(size);
  final view = ByteData.sublistView(out);
  var at = 0;
  for (final f in frames) {
    view.setUint32(at, f.length);
    out.setRange(at + 4, at + 4 + f.length, f);
    at += 4 + f.length;
  }
  return out;
}

List<Uint8List> decodeRelayBundle(Uint8List bundle) {
  final out = <Uint8List>[];
  final view = ByteData.sublistView(bundle);
  var at = 0;
  while (at < bundle.length) {
    if (at + 4 > bundle.length) throw const NearSyncError('bad_bundle');
    final n = view.getUint32(at);
    if (at + 4 + n > bundle.length) throw const NearSyncError('bad_bundle');
    out.add(Uint8List.sublistView(bundle, at + 4, at + 4 + n));
    at += 4 + n;
  }
  return out;
}

class NearRelayPipe implements NearPipe {
  NearRelayPipe({
    required this.host,
    required this.put,
    required this.take,
    this.linger = kRelayLinger,
    this.idle = kRelayIdle,
  });

  final bool host;
  final RelayPut put;
  final RelayTake take;
  final Duration linger;
  final Duration idle;

  final _frames = StreamController<Uint8List>();
  final _queue = <Uint8List>[];
  var _queued = 0;
  var _sendSeq = 0;
  var _takeSeq = 0;
  var _closed = false;
  Timer? _timer;
  Future<void> _flushing = Future.value();

  String get _mine => host ? 'h' : 'j';
  String get _theirs => host ? 'j' : 'h';

  @override
  Stream<Uint8List> get frames => _frames.stream;

  void start() => unawaited(_pollLoop());

  @override
  Future<void> send(Uint8List frame) async {
    if (_closed) throw StateError('relay closed');
    _queue.add(Uint8List.fromList(frame));
    _queued += 4 + frame.length;
    if (_queued >= kRelayBundle) {
      await _flush();
    } else {
      _timer ??= Timer(linger, () {
        _timer = null;
        unawaited(_flush());
      });
    }
  }

  Future<void> _flush() {
    _timer?.cancel();
    _timer = null;
    if (_queue.isEmpty || _closed) return _flushing;
    final bundle = encodeRelayBundle(_queue);
    _queue.clear();
    _queued = 0;
    final seq = _sendSeq++;
    _flushing = _flushing.then((_) => _putWithRetry(seq, bundle));
    return _flushing;
  }

  Future<void> _putWithRetry(int seq, Uint8List bundle) async {
    var wait = const Duration(milliseconds: 500);
    for (var attempt = 0; attempt < 4; attempt++) {
      if (_closed) return;
      try {
        await put(_mine, seq, bundle);
        return;
      } catch (_) {
        await Future<void>.delayed(wait);
        wait *= 2;
      }
    }
    _fail();
  }

  Future<void> _pollLoop() async {
    var errors = 0;
    while (!_closed) {
      Uint8List? got;
      try {
        got = await take(_theirs, _takeSeq);
        errors = 0;
      } catch (_) {
        errors += 1;
        if (errors >= 5) {
          _fail();
          return;
        }
        await Future<void>.delayed(const Duration(seconds: 1));
        continue;
      }
      if (_closed) return;
      if (got == null) {
        await Future<void>.delayed(idle);
        continue;
      }
      _takeSeq += 1;
      final List<Uint8List> frames;
      try {
        frames = decodeRelayBundle(got);
      } catch (_) {
        _fail();
        return;
      }
      for (final f in frames) {
        if (!_frames.isClosed) _frames.add(f);
      }
    }
  }

  void _fail() {
    if (_frames.isClosed) return;
    _frames.addError(const NearSyncError('relay_failed'));
    close();
  }

  void close() {
    _closed = true;
    _timer?.cancel();
    _timer = null;
    if (!_frames.isClosed) unawaited(_frames.close());
  }
}
