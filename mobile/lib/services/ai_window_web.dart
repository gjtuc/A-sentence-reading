/// design/432 - the AI page in its own small window over this one, so closing
/// it comes straight back to the app instead of to a browser tab.
library;

import 'package:web/web.dart' as web;

const String _kName = 'asr_ai';

bool open(String url) {
  try {
    final win = web.window;
    final s = win.screen;
    final w = (s.availWidth * 0.55).round().clamp(480, s.availWidth).toInt();
    final h = (s.availHeight * 0.85).round().clamp(400, s.availHeight).toInt();
    final left = win.screenX + ((win.outerWidth - w) / 2).round();
    final top = win.screenY + ((win.outerHeight - h) / 2).round();
    final ai = win.open(url, _kName, 'popup=yes,width=$w,height=$h,left=$left,top=$top');
    if (ai == null) return false;
    ai.focus();
    return true;
  } catch (_) {
    return false;
  }
}
