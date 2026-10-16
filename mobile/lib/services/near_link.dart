/// design/410 — the WebRTC side of near sync (web hosts, phone joins).
///
/// Only the two session descriptions pass the server (`/api/near/links`). Candidates
/// are gathered before the description is sent, so there is no trickle round trip.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../api/client.dart';
import 'evidence_bus.dart';
import 'near_sync.dart';

enum NearStep { idle, preparing, waiting, connecting, syncing, done, failed }

const Duration kNearLinkLife = Duration(minutes: 3);
const Duration kNearOpenLimit = Duration(seconds: 30);
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

  RTCPeerConnection? _pc;
  RTCDataChannel? _channel;
  _RtcPipe? _pipe;
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
      await opened.timeout(
        kNearOpenLimit,
        onTimeout: () => throw const NearSyncError('open_timeout'),
      );
      await _sync(channel);
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
      final channel = await gotChannel.future.timeout(
        kNearOpenLimit,
        onTimeout: () => throw const NearSyncError('open_timeout'),
      );
      await _whenOpen(channel).timeout(
        kNearOpenLimit,
        onTimeout: () => throw const NearSyncError('open_timeout'),
      );
      await _sync(channel);
    });
  }

  Future<void> cancel() async {
    if (step == NearStep.done || step == NearStep.failed) return;
    _stopped = true;
    code = 'cancelled';
    _pipe?.end();
    _go(NearStep.failed);
    await _close();
  }

  Future<void> _guard(Future<void> Function() run) async {
    final watch = Stopwatch()..start();
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
        'papers_in': r?.papersIn ?? 0,
        'papers_out': r?.papersOut ?? 0,
        'papers_failed': r?.failed.length ?? 0,
        'progress_rows': r?.progressRows ?? 0,
        'bytes_in': progress.bytesIn,
        'bytes_out': progress.bytesOut,
        'ms': ms,
      },
    );
  }

  Future<RTCPeerConnection> _peer() async {
    final pc = await createPeerConnection(_ice);
    _pc = pc;
    pc.onConnectionState = (state) {
      if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed) {
        if (code.isEmpty) code = 'ice_failed';
        _pipe?.end();
      }
    };
    return pc;
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
        _pipe?.end();
      }
    };
    return open.future;
  }

  Future<void> _sync(RTCDataChannel channel) async {
    if (_stopped) throw const NearSyncError('cancelled');
    _go(NearStep.syncing);
    final pipe = _RtcPipe(channel);
    _pipe = pipe;
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
    _pipe?.end();
    final channel = _channel;
    final pc = _pc;
    _channel = null;
    _pc = null;
    if (_linkId.isNotEmpty && _host && step != NearStep.done) {
      unawaited(client.nearDropLink(_linkId));
    }
    try {
      await channel?.close();
    } catch (_) {}
    try {
      await pc?.close();
    } catch (_) {}
  }
}
