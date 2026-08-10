import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/upload_notify.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('AsrStatus parses mobile_upload_background kill switch', () {
    final on = AsrStatus.fromJson({
      'ok': true,
      'version': '0.2.91',
      'mobile_upload_background': true,
    });
    expect(on.mobileUploadBackground, isTrue);

    final off = AsrStatus.fromJson({
      'ok': true,
      'version': '0.2.91',
      'mobile_upload_background': false,
    });
    expect(off.mobileUploadBackground, isFalse);

    // EDGE: older Cloud Run without the key → allow FG (kill needs explicit false).
    final missing = AsrStatus.fromJson({'ok': true, 'version': '0.2.90'});
    expect(missing.mobileUploadBackground, isTrue);
  });

  test('sanitizeNotifyStage strips secrets-like text', () {
    expect(ChannelUploadNotify.sanitizeNotifyStage('조각 올리는 중'), '조각 올리는 중');
    expect(ChannelUploadNotify.sanitizeNotifyStage(''), '처리 중');
    expect(
      ChannelUploadNotify.sanitizeNotifyStage('a' * 80).length,
      lessThanOrEqualTo(48),
    );
    // WHY: never put emails / absolute paths into notification text.
    expect(ChannelUploadNotify.sanitizeNotifyStage('user@example.com'), '처리 중');
    expect(
      ChannelUploadNotify.sanitizeNotifyStage(r'C:\Users\secret\a.pdf'),
      '처리 중',
    );
    expect(
      ChannelUploadNotify.sanitizeNotifyStage('/data/user/0/com.x/cache'),
      '처리 중',
    );
  });

  test('NoopUploadNotify pending open is single-consume', () async {
    final n = NoopUploadNotify();
    await n.showCompleted(cacheId: 'cache_abc123');
    final first = await n.takePendingOpenCacheId();
    expect(first, 'cache_abc123');
    final second = await n.takePendingOpenCacheId();
    expect(second, isNull);
  });

  test('NoopUploadNotify ignores empty completed cache id', () async {
    final n = NoopUploadNotify();
    await n.showCompleted(cacheId: '   ');
    expect(await n.takePendingOpenCacheId(), isNull);
  });
}
