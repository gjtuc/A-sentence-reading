import 'pane_link.dart';

/// No second window off the web.
PaneChannel? openPaneChannel(String name) => null;

bool openWindow(String url, String name) => false;

void onPageHide(void Function() handler) {}
