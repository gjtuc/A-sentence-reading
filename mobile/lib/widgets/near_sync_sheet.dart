/// design/410 — "폰과 동기화" (web) / "웹과 동기화" (phone) dialog.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../services/near_library_local.dart';
import '../services/near_link.dart';
import '../services/shadowing_disk_store.dart';
import '../state/library_controller.dart';

String nearSyncTitle() => kIsWeb ? '폰과 동기화' : '웹과 동기화';

/// Plain Korean for a failure code from [NearLink.code].
String nearFailText(String code) {
  switch (code) {
    case 'no_link':
      return '열린 웹 연결이 없습니다. PC 웹에서 먼저 「폰과 동기화」를 누른 뒤 다시 눌러 주세요.';
    case 'no_phone':
      return '3분 동안 폰이 연결하지 않았습니다. 다시 시도해 주세요.';
    case 'usb_no_web':
      return '3분 동안 PC 웹이 연결하지 않았습니다. PC 웹에서 「폰과 동기화」를 누른 뒤 다시 해 주세요.';
    case 'usb_gone':
      return 'USB 연결이 끊겼습니다. 선과 PC의 「USB 동기화 도우미」가 켜져 있는지 보고 다시 해 주세요.';
    case 'open_timeout':
    case 'ice_failed':
      return '두 기기가 서로 닿지 못했습니다. 다시 해 주세요.';
    case 'pipe_error':
    case 'relay_failed':
      return '서버를 거쳐 옮기다가 끊겼습니다. 다시 하면 남은 것만 옮깁니다.';
    case 'cancelled':
      return '취소했습니다.';
    case 'quiet':
    case 'closed':
      return '주고받는 중에 연결이 끊겼습니다. 다시 하면 남은 것만 옮깁니다.';
    default:
      if (code.startsWith('server_')) {
        return '서버와 연결하지 못했습니다 ($code). 잠시 뒤 다시 해 주세요.';
      }
      return '동기화하지 못했습니다 ($code).';
  }
}

String _mb(int bytes) => (bytes / (1024 * 1024)).toStringAsFixed(1);

Future<void> showNearSyncSheet({
  required BuildContext context,
  required LibraryController library,
}) async {
  final uid = await library.progressUid();
  if (!context.mounted) return;
  final link = NearLink(
    client: library.apiClient,
    local: LibraryNearLocal(
      disk: library.paperDiskStore,
      uid: uid,
      shadow: ShadowingDiskStore()..bindUid(library.diskUid ?? uid),
      loadGone: library.nearGone,
      hiddenIds: library.nearHiddenIds,
      onForget: library.forgetFromNear,
    ),
  );
  if (kIsWeb) {
    unawaited(link.host());
  } else {
    unawaited(link.join());
  }
  await showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => _NearSyncDialog(link: link),
  );
  await link.cancel();
  final r = link.report;
  await library.nearServerDeletesSettled();
  if (r != null && (r.papersIn > 0 || r.progressRows > 0 || r.papersGone > 0)) {
    await library.refresh(trigger: 'near_sync');
  }
  link.dispose();
}

class _NearSyncDialog extends StatelessWidget {
  const _NearSyncDialog({required this.link});

  final NearLink link;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: link,
      builder: (context, _) {
        final finished =
            link.step == NearStep.done || link.step == NearStep.failed;
        return AlertDialog(
          title: Text(nearSyncTitle()),
          content: SizedBox(
            width: 360,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!finished) const LinearProgressIndicator(),
                if (!finished) const SizedBox(height: 16),
                Text(_line()),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(finished ? '닫기' : '취소'),
            ),
          ],
        );
      },
    );
  }

  String _line() {
    final p = link.progress;
    switch (link.step) {
      case NearStep.idle:
      case NearStep.preparing:
        return '연결을 준비하고 있습니다…';
      case NearStep.waiting:
        if (link.via == 'usb') {
          return kIsWeb
              ? 'USB 선으로 연결된 폰을 찾았습니다.\n'
                  '이제 폰에서 「웹과 동기화」 버튼을 눌러 주세요. (3분 안에)'
              : 'USB 선으로 PC와 이었습니다.\n'
                  '이제 PC 웹에서 「폰과 동기화」 버튼을 눌러 주세요. (3분 안에)';
        }
        return '이제 폰에서 라이브러리 위쪽의 「웹과 동기화」 버튼을 눌러 주세요.\n'
            '(같은 계정으로 로그인한 폰, 3분 안에)';
      case NearStep.connecting:
        return '두 기기를 잇고 있습니다…\n'
            '(바로 연결되지 않으면 10초 뒤 서버를 거쳐 옮깁니다)';
      case NearStep.syncing:
        final how = switch (link.via) {
          'usb' => 'USB 선으로 옮기는 중',
          'relay' => '서버를 거쳐 옮기는 중',
          _ => '직접 연결로 옮기는 중',
        };
        return [
          how,
          '논문 받는 중 ${p.gotIn}/${p.wantIn} (${_mb(p.bytesIn - p.extraBytesIn)}MB)',
          '논문 보내는 중 ${p.sentOut}/${p.wantOut} (${_mb(p.bytesOut - p.extraBytesOut)}MB)',
          if (p.extraBytesIn > 0) '연습 녹음·기록 받는 중 (${_mb(p.extraBytesIn)}MB)',
          if (p.extraBytesOut > 0) '연습 녹음·기록 보내는 중 (${_mb(p.extraBytesOut)}MB)',
          if (p.extraBytesIn > 0 || p.extraBytesOut > 0)
            '(처음 한 번은 연습 녹음을 모두 옮겨서 오래 걸립니다. 다음부터는 새것만 옮깁니다)',
        ].join('\n');
      case NearStep.done:
        final r = link.report;
        if (r == null) return '끝났습니다.';
        final lines = <String>[
          '끝났습니다.',
          '받은 논문 ${r.papersIn}개, 보낸 논문 ${r.papersOut}개',
          if (r.papersGone > 0) '다른 기기에서 지운 논문 ${r.papersGone}개를 여기서도 지움',
          '읽던 위치 ${r.progressRows}개 맞춤',
          if (r.extrasIn > 0)
            '연습 녹음·기록 ${r.extrasIn}개 받음 (${_mb(p.extraBytesIn)}MB)',
          if (p.extraBytesOut > 0) '연습 녹음·기록 보냄 (${_mb(p.extraBytesOut)}MB)',
          if (r.failed.isNotEmpty) '받지 못한 논문 ${r.failed.length}개',
        ];
        return lines.join('\n');
      case NearStep.failed:
        return nearFailText(link.code);
    }
  }
}
