/// design/372 — the mirror must not be readable by gallery apps.
///
/// The mirror lives in public storage on purpose: app-private storage is wiped
/// by the uninstall design/262 exists to survive. Public storage is exactly what
/// the media scanner reads, so every mirrored figure showed up in the gallery.
library;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sentence_reading/platform/documents_mirror_channel.dart';
import 'package:sentence_reading/services/documents_mirror_store.dart';

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

  test('design/372 the mirror is marked once per bind', () async {
    var calls = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls += 1;
      return {'ok': true, 'created': calls == 1, 'path': '/x/.nomedia'};
    });
    final store = DocumentsMirrorStore();
    // Not bound yet: nothing to mark, and asking would reach for a uid that is
    // not there.
    expect(await store.hideFromGalleryOnce(), isFalse);
    expect(calls, 0);

    store.bindUid('116191504131668885631');
    expect(await store.hideFromGalleryOnce(), isTrue);
    // A rescan per launch is enough. Per mirrored paper would be work for
    // nothing, because the marker written on bind already stops new indexing.
    expect(await store.hideFromGalleryOnce(), isTrue);
    expect(calls, 1);

    // A new sign-in is a new tree to check.
    store.bindUid('999888777666555444');
    expect(await store.hideFromGalleryOnce(), isTrue);
    expect(calls, 2);
  });
}
