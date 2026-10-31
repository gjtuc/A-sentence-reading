/// design/495 — settings row for the PC helper (논문 전송 도우미).
///
/// Quiet on purpose: no prompt elsewhere in the app. The green check shows only
/// when the helper answers (web: its /store socket; phone: the probe port over
/// the USB cable).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/helper_store.dart';

const String kHelperName = '논문 전송 도우미';
const String kHelperPointUsb =
    '① 도우미를 설치하면 휴대폰과 컴퓨터 사이에서 논문을 USB 선으로 바로 옮겨 줘요.';
const String kHelperPointKeep =
    '② 브라우저 기록을 지우면 이 컴퓨터에 받아 둔 논문도 함께 지워져요. '
    '도우미를 설치하면 브라우저 기록을 지워도 이 컴퓨터에 보관한 논문이 다시 돌아와요.';
const String kHelperWithout = '도우미가 없어도 동기화는 돼요. 대신 인터넷을 거쳐 조금 느릴 수 있어요.';
const String kHelperConnected = '도우미 연결됨';

const List<String> kHelperInstallSteps = [
  '① 아래 「파일 받기」를 눌러 도우미 파일을 받아요.',
  '② 크롬이 「의심스러운 파일 차단됨」이라고 하면, 다운로드 목록에서 그 파일을 눌러 「다운로드」를 눌러요. '
      '엣지는 「…」를 눌러 「유지」를 눌러요. 처음 보는 프로그램이라 막는 것이고, 바이러스가 있다는 뜻은 아니에요.',
  '③ 받은 파일을 두 번 눌러 실행해요. 「Windows의 PC 보호」 창이 뜨면 「추가 정보」를 누르고 「실행」을 눌러요.',
  '④ 「설치했어요」 창이 뜨면 끝이에요. 컴퓨터를 켜면 도우미가 저절로 켜져요.',
  '⑤ 휴대폰을 USB 선으로 컴퓨터에 연결해요. 휴대폰에서 USB 디버깅을 켜 두어야 해요. 켜는 법은 휴대폰 앱의 설정에 있어요.',
  '⑥ 브라우저가 「로컬 네트워크의 기기」를 찾아도 되는지 물으면 「허용」을 눌러요.',
];

const String kHelperAutoSync = '설치하고 나면, 웹과 휴대폰 앱을 열어 둔 채 선을 꽂을 때 알아서 맞춰요.';
const String kHelperOldWeb = '새 도우미가 나왔어요. 「도우미 받기」로 다시 받아 설치해 주세요.';
const String kHelperOldPhone = '새 도우미가 나왔어요. 컴퓨터 웹의 설정에서 다시 받아 설치해 주세요.';

const List<String> kUsbDebugSteps = [
  '① 아래 「개발자 설정 열기」를 눌러요. 개발자 설정이 아직 없으면 「휴대폰 정보」가 열려요. '
      '「빌드 번호」를 일곱 번 눌러 개발자 설정을 켠 뒤 다시 눌러요. '
      '삼성 휴대폰은 「휴대폰 정보 > 소프트웨어 정보」 안에 빌드 번호가 있어요.',
  '② 개발자 설정에서 「USB 디버깅」을 켜요.',
  '③ 휴대폰을 컴퓨터에 USB 선으로 연결해요. 「USB 디버깅을 허용할까요?」가 뜨면 '
      '「이 컴퓨터에서 항상 허용」에 체크하고 「허용」을 눌러요.',
];

const MethodChannel _usbDebug = MethodChannel('asr/usb_debug');

bool get _android => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

class HelperSettingsTile extends StatefulWidget {
  const HelperSettingsTile({super.key, required this.downloadUrl});

  final String downloadUrl;

  @override
  State<HelperSettingsTile> createState() => _HelperSettingsTileState();
}

class _HelperSettingsTileState extends State<HelperSettingsTile> {
  bool _connected = false;
  bool _old = false;
  bool? _usbDebugOn;

  @override
  void initState() {
    super.initState();
    unawaited(_check());
  }

  Future<void> _check({bool ask = false}) async {
    var connected = false;
    var old = false;
    bool? usb;
    if (kIsWeb) {
      final opened = await connectHelperStore(ask: ask);
      if (opened != null) {
        connected = true;
        old = helperIsOld(opened.$2);
        await opened.$1.close();
      }
    } else if (_android) {
      final hello = await probeHelperFromPhone();
      connected = hello != null;
      old = helperIsOld(hello);
      try {
        final st = await _usbDebug.invokeMapMethod<String, Object?>('state');
        usb = st?['adb'] == true;
      } catch (_) {}
    }
    if (!mounted) return;
    setState(() {
      _connected = connected;
      _old = old;
      _usbDebugOn = usb;
    });
  }

  Future<void> _download() async {
    final uri = Uri.tryParse(widget.downloadUrl.trim());
    if (uri == null || widget.downloadUrl.trim().isEmpty) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('도우미 파일을 받지 못했어요.')),
      );
    }
  }

  Future<void> _openDeveloperSettings() async {
    try {
      await _usbDebug.invokeMethod<String>('openDeveloperSettings');
    } catch (_) {}
  }

  Future<void> _showGuide() async {
    if (kIsWeb) markHelperWanted();
    const web = kIsWeb;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        final theme = Theme.of(ctx);
        const steps = web ? kHelperInstallSteps : kUsbDebugSteps;
        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  web ? '$kHelperName 설치' : 'USB 디버깅 켜는 법',
                  style: theme.textTheme.titleMedium,
                ),
                if (web) ...[
                  const SizedBox(height: 4),
                  Text('Windows 컴퓨터에서 쓸 수 있어요.', style: theme.textTheme.bodySmall),
                ],
                const SizedBox(height: 12),
                for (final s in steps)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Text(s, style: theme.textTheme.bodyMedium),
                  ),
                if (web) ...[
                  Text(kHelperAutoSync, style: theme.textTheme.bodyMedium),
                  const SizedBox(height: 10),
                ],
                Text(
                  web
                      ? '지우려면 Windows 설정 > 앱에서 「논문 전송 도우미 (문장 읽기)」를 지우면 돼요. 보관한 논문 사본은 남아요.'
                      : '도우미 파일은 컴퓨터 웹의 설정 > $kHelperName 에서 받을 수 있어요.',
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('닫기'),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: web
                          ? (widget.downloadUrl.trim().isEmpty ? null : _download)
                          : _openDeveloperSettings,
                      child: const Text(web ? '파일 받기' : '개발자 설정 열기'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
    await _check(ask: web);
  }

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb && !_android) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final small = theme.textTheme.bodySmall;
    final ok = Colors.green.shade600;
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text(kHelperName, style: theme.textTheme.titleSmall),
              if (_connected) ...[
                const SizedBox(width: 8),
                Icon(Icons.check_circle, color: ok, size: 18),
                const SizedBox(width: 4),
                Text(kHelperConnected, style: small?.copyWith(color: ok)),
              ],
            ],
          ),
          if (_connected && _old) ...[
            const SizedBox(height: 4),
            Text(
              kIsWeb ? kHelperOldWeb : kHelperOldPhone,
              style: small?.copyWith(color: theme.colorScheme.primary),
            ),
          ],
          const SizedBox(height: 6),
          Text(kHelperPointUsb, style: small),
          if (kIsWeb) ...[
            const SizedBox(height: 4),
            Text(kHelperPointKeep, style: small),
          ],
          const SizedBox(height: 4),
          Text(
            kHelperWithout,
            style: small?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          if (_android && _usbDebugOn != null) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(
                  _usbDebugOn! ? Icons.check_circle : Icons.info_outline,
                  size: 18,
                  color: _usbDebugOn! ? ok : theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: 4),
                Text(_usbDebugOn! ? 'USB 디버깅 켜짐' : 'USB 디버깅 꺼짐', style: small),
              ],
            ),
          ],
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.tonal(
              onPressed: _showGuide,
              child: const Text(kIsWeb ? '도우미 받기' : 'USB 디버깅 켜는 법'),
            ),
          ),
        ],
      ),
    );
  }
}
