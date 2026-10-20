/// design/432 - on the web, the AI page opens in its own window, and this
/// window's full screen comes back on the next click here.
library;

import 'ai_window_stub.dart' if (dart.library.js_interop) 'ai_window_web.dart' as impl;
import 'full_screen.dart';

/// False off the web or when the browser refused; the caller then launches.
bool openAiWindow(Uri url) {
  fullScreenStepAway();
  return impl.open(url.toString());
}
