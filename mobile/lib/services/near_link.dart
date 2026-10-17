/// design/410 — the WebRTC side of near sync (web hosts, phone joins).
///
/// Only the two session descriptions pass the server (`/api/near/links`). Candidates
/// are gathered before the description is sent, so there is no trickle round trip.
/// When the channel does not open within [kNearDirectLimit], both sides run the same
/// frames through the server relay instead (`near_relay.dart`).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../api/client.dart';
import 'evidence_bus.dart';
import 'near_relay.dart';
import 'near_sync.dart';

enum NearStep { idle, preparing, waiting, connecting, syncing, done, failed }

const Duration kNearLinkLife = Duration(minutes: 3);
const Duration kNearOpenLimit = Duration(seconds: 30);
const Duration kNearDirectLimit = Duration(seconds: 10);
const Duration kNearGatherLimit = Duration(seconds: 4);
const Duration kNearPollEvery = Duration(milliseconds: 1500);

const Map<String, dynamic> _ice = {
  'iceServers': [
    {'urls': 'stun:stun.l.google.com:19302'},
  ],
};

class _RtcPipe implements NearPipe {
  _RtcPipe(this.channel) {
    channel.onMessage = (message) {
      if (_frames.isClosed) return;
      if (message.isBinary) {
        _frames.add(message.binary);
      } else {
        _frames.add(Uint8List.fromList(message.text.codeUnits));
      }
    };
  }

  final RTCDataChannel channel;
  final _frames = StreamController<Uint8List>();

  @override
  Stream<Uint8List> get frames => _frames.stream;

  @override
  Future<void> send(Uint8List frame) =>
      channel.send(RTCDataChannelMessage.fromBinary(frame));

  void end() {
    if (!_frames.isClosed) unawaited(_frames.close());
  }
}

class NearLink extends ChangeNotifier {
  NearLink({required this.client, required this.local});

  final AsrClient client;
  final NearLocal local;

  NearStep step = NearStep.idle;
  String code = '';
  NearSyncProgress progress = const NearSyncProgress();
  NearSyncReport? report;

  /// `direct` (WebRTC) or `relay` (through the server).
  String via = '';

  RTCPeerConnection? _pc;
  RTCDataChannel? _channel;
  void Function()? _endPipe;
  final _watch = Stopwatch();
  int _openMs = -1;
  Map<String, Object> _path = const {};
  String _linkId = '';
  bool _host = false;
  bool _stopped = false;

  void _go(NearStep next) {
    if (_stopped && next != NearStep.failed && next != NearStep.done) return;
    step = next;
    notifyListeners();
  }

  /// Web: publish an offer and wait for the phone.
  Future<void> host() async {
    _host = true;
    await _guard(() async {
      _go(NearStep.preparing);
      final pc = await _peer();
      final channel = await pc.createDataChannel(
        'asr-near',
        RTCDataChannelInit()..ordered = true,
      );
      final opened = _whenOpen(channel);
      final offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      final local = await _gathered(pc);
      _linkId = await client.nearCreateLink(local);
      _go(NearStep.waiting);
      final answer = await _awaitAnswer();
      _go(NearStep.connecting);
      await pc.setRemoteDescription(
        RTCSessionDescription('${answer['sdp']}', '${answer['type']}'),
      );
      unawaited(client.nearDropLink(_linkId));
      if (await _within(opened)) {
        await _direct(channel);
      } else {
        await _relay();
      }
    });
  }

  /// Phone: take this account's open link and answer it.
  Future<void> join() async {
    _host = false;
    await _guard(() async {
      _go(NearStep.preparing);
      final link = await client.nearClaimLink();
      if (link == null) throw const NearSyncError('no_link');
      _linkId = link.linkId;
      final pc = await _peer();
      final gotChannel = Completer<RTCDataChannel>();
      pc.onDataChannel = (channel) {
        if (!gotChannel.isCompleted) gotChannel.complete(channel);
      };
      await pc.setRemoteDescription(
        RTCSessionDescription('${link.offer['sdp']}', '${link.offer['type']}'),
      );
      final answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      final local = await _gathered(pc);
      await client.nearPutAnswer(_linkId, local);
      _go(NearStep.connecting);
      if (await _within(gotChannel.future.then(_whenOpen))) {
        await _direct(_channel!);
      } else {
        await _relay();
      }
    });
  }

  Future<void> cancel() async {
    if (step == NearStep.done || step == NearStep.failed) return;
    _stopped = true;
    code = 'cancelled';
    _endPipe?.call();
    _go(NearStep.failed);
    await _close();
  }

  Future<void> _guard(Future<void> Function() run) async {
    final watch = _watch..start();
    try {
      await run();
      _go(NearStep.done);
    } on NearSyncError catch (e) {
      if (code.isEmpty) code = e.code;
      _go(NearStep.failed);
    } on AsrApiException catch (e) {
      if (code.isEmpty) code = 'server_${e.statusCode ?? 0}';
      _go(NearStep.failed);
    } catch (_) {
      if (code.isEmpty) code = 'rtc_error';
      _go(NearStep.failed);
    } finally {
      await _close();
      _record(watch.elapsedMilliseconds);
    }
  }

  void _record(int ms) {
    final ok = step == NearStep.done;
    final r = report;
    asrEvidenceBus?.record(
      'near_sync_done',
      severity: ok ? 'lifecycle' : 'error',
      stage: _host ? 'host' : 'join',
      ok: ok,
      message: ok ? '' : code,
      details: {
        'web': kIsWeb ? 1 : 0,
        'relay': via == 'relay' ? 1 : 0,
        'papers_in': r?.papersIn ?? 0,
        'papers_out': r?.papersOut ?? 0,
        'papers_failed': r?.failed.length ?? 0,
        'progress_rows': r?.progressRows ?? 0,
        'bytes_in': progress.bytesIn,
        'bytes_out': progress.bytesOut,
        'extra_bytes_in': progress.extraBytesIn,
        'extra_bytes_out': progress.extraBytesOut,
        'ms': ms,
        'open_ms': _openMs,
        'extras_in': r?.extrasIn ?? 0,
        'extras_out': r?.extrasOut ?? 0,
        ...?r?.times,
        ..._path,
      },
    );
  }

  Future<RTCPeerConnection> _peer() async {
    final pc = await createPeerConnection(_ice);
    _pc = pc;
    pc.onConnectionState = (state) {
      if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed) {
        if (code.isEmpty && via == 'direct') code = 'ice_failed';
        if (via == 'direct') _endPipe?.call();
      }
    };
    return pc;
  }

  /// The selected candidate pair: kinds (host / srflx / prflx / relay), protocol
  /// and round trip time. Empty when the stats do not say.
  Future<Map<String, Object>> _pathStats() async {
    final pc = _pc;
    if (pc == null) return const {};
    try {
      final reports = await pc.getStats();
      final byId = {for (final r in reports) r.id: r};
      StatsReport? pair;
      for (final r in reports) {
        if (r.type != 'transport') continue;
        final sel = byId['${r.values['selectedCandidatePairId'] ?? ''}'];
        if (sel != null) pair = sel;
      }
      if (pair == null) {
        for (final r in reports) {
          if (r.type == 'candidate-pair' &&
              r.values['state'] == 'succeeded' &&
              r.values['nominated'] == true) {
            pair = r;
            break;
          }
        }
      }
      if (pair == null) return const {};
      final local = byId['${pair.values['localCandidateId'] ?? ''}'];
      final remote = byId['${pair.values['remoteCandidateId'] ?? ''}'];
      String word(Object? v) => '${v ?? ''}'.trim().toLowerCase();
      final rtt = pair.values['currentRoundTripTime'];
      return {
        'local_kind': word(local?.values['candidateType']),
        'remote_kind': word(remote?.values['candidateType']),
        'proto': word(local?.values['protocol']),
        'rtt_ms': rtt is num ? (rtt * 1000).round() : -1,
      };
    } catch (_) {
      return const {};
    }
  }

  Future<Map<String, Object?>> _gathered(RTCPeerConnection pc) async {
    final until = DateTime.now().add(kNearGatherLimit);
    while (DateTime.now().isBefore(until)) {
      if (pc.iceGatheringState ==
          RTCIceGatheringState.RTCIceGatheringStateComplete) {
        break;
      }
      await Future<void>.delayed(const Duration(milliseconds: 100));
    }
    final desc = await pc.getLocalDescription();
    final sdp = desc?.sdp ?? '';
    if (sdp.isEmpty) throw const NearSyncError('no_local_description');
    return {'type': desc?.type ?? '', 'sdp': sdp};
  }

  Future<Map<String, dynamic>> _awaitAnswer() async {
    final until = DateTime.now().add(kNearLinkLife);
    while (DateTime.now().isBefore(until)) {
      if (_stopped) throw const NearSyncError('cancelled');
      final answer = await client.nearPeekAnswer(_linkId);
      if (answer != null) return answer;
      await Future<void>.delayed(kNearPollEvery);
    }
    throw const NearSyncError('no_phone');
  }

  Future<void> _whenOpen(RTCDataChannel channel) {
    _channel = channel;
    final open = Completer<void>();
    if (channel.state == RTCDataChannelState.RTCDataChannelOpen) {
      open.complete();
    }
    channel.onDataChannelState = (state) {
      if (state == RTCDataChannelState.RTCDataChannelOpen) {
        if (!open.isCompleted) open.complete();
      } else if (state == RTCDataChannelState.RTCDataChannelClosed) {
        if (via == 'direct') _endPipe?.call();
      }
    };
    return open.future;
  }

  Future<bool> _within(Future<void> opened) async {
    try {
      await opened.timeout(kNearDirectLimit);
      return true;
    } on TimeoutException {
      return false;
    }
  }

  Future<void> _direct(RTCDataChannel channel) async {
    via = 'direct';
    _openMs = _watch.elapsedMilliseconds;
    _path = await _pathStats();
    final pipe = _RtcPipe(channel);
    _endPipe = pipe.end;
    await _sync(pipe);
  }

  Future<void> _relay() async {
    via = 'relay';
    _openMs = _watch.elapsedMilliseconds;
    final pc = _pc;
    final channel = _channel;
    _pc = null;
    _channel = null;
    pc?.onConnectionState = null;
    channel?.onDataChannelState = null;
    try {
      await channel?.close();
    } catch (_) {}
    try {
      await pc?.close();
    } catch (_) {}
    final linkId = _linkId;
    final pipe = NearRelayPipe(
      host: _host,
      put: (side, seq, bundle) =>
          client.nearRelayPut(linkId, side, seq, bundle),
      take: (side, seq) => client.nearRelayTake(linkId, side, seq),
    );
    _endPipe = pipe.close;
    pipe.start();
    await _sync(pipe);
  }

  Future<void> _sync(NearPipe pipe) async {
    if (_stopped) throw const NearSyncError('cancelled');
    _go(NearStep.syncing);
    report = await NearSync(
      pipe,
      local,
      onProgress: (p) {
        progress = p;
        notifyListeners();
      },
    ).run();
    // The last `fin` must leave before the channel closes.
    await Future<void>.delayed(const Duration(seconds: 1));
  }

  Future<void> _close() async {
    _endPipe?.call();
    final channel = _channel;
    final pc = _pc;
    _channel = null;
    _pc = null;
    if (_linkId.isNotEmpty && _host && step != NearStep.done) {
      unawaited(client.nearDropLink(_linkId));
    }
    if (via == 'relay' && step != NearStep.done) {
      unawaited(client.nearRelayWipe(_linkId));
    }
    try {
      await channel?.close();
    } catch (_) {}
    try {
      await pc?.close();
    } catch (_) {}
  }
}
