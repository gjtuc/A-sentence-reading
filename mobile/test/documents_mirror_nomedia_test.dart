/// design/372 — the mirror must not be readable by gallery apps.
///
/// The mirror lives in public storage on purpose: app-private storage is wiped
/// by the uninstall design/262 exists to survive. Public storage is exactly what
/// the media scanner reads, so every mirrored figure showed up in the gallery.
library;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sentence_reading/platform/documents_mirror_channel.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('asr/documents_mirror');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test('design/372 a marked mirror reports hidden', () async {
    final calls = <String>[];
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      return {'ok': true, 'created': true, 'path': '/x/.nomedia'};
    });
    expect(await DocumentsMirrorChannel().hideFromGallery(), isTrue);
    expect(calls, ['hideFromGallery']);
  });

  test('design/372 an already-marked mirror is still a success', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      // `created` false means this call did not write the marker. Reading that
      // as failure would raise the banner every time the app opened.
      return {'ok': true, 'created': false, 'path': '/x/.nomedia'};
    });
    expect(await DocumentsMirrorChannel().hideFromGallery(), isTrue);
  });

  test('design/372 a refused permission is not reported as hidden', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      throw PlatformException(code: 'no_permission');
    });
    // Fail-closed the honest way: say it is not hidden. Claiming it is would
    // leave the figures in the gallery with nothing saying why.
    expect(await DocumentsMirrorChannel().hideFromGallery(), isFalse);
  });

  test('design/372 a reply that is not a map is not hidden', () async {
    messenger.setMockMethodCallHandler(channel, (call) async => true);
    // An older build with no such method answers something else. It must not
    // count, or the mirror would look marked on a phone where it is not.
    expect(await DocumentsMirrorChannel().hideFromGallery(), isFalse);
  });

  test('design/372 ok false is not hidden', () async {
    messenger.setMockMethodCallHandler(
      channel,
      (call) async => {'ok': false, 'created': false},
    );
    expect(await DocumentsMirrorChannel().hideFromGallery(), isFalse);
  });
}
