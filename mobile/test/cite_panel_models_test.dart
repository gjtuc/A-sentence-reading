import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/cite_panel_models.dart';

void main() {
  test('parseCitePanelEnabledPref defaults on', () {
    expect(parseCitePanelEnabledPref(null), isTrue);
    expect(parseCitePanelEnabledPref(''), isTrue);
    expect(parseCitePanelEnabledPref('{"enabled":false}'), isFalse);
    expect(parseCitePanelEnabledPref('{"enabled":true}'), isTrue);
  });

  test('citePanelPrefsKey scopes by uid', () {
    expect(citePanelPrefsKey(null), kCitePanelPrefsKeyBase);
    expect(citePanelPrefsKey('u1'), '$kCitePanelPrefsKeyBase.u1');
  });
}
