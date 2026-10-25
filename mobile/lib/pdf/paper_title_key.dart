/// design/457 — a paper's title as a key shared by every device of the account.
///
/// Another download of the same paper has a different PDF hash, so the import list
/// also knows a paper by this key. Short or generic titles give no key: matching
/// "Introduction" would mark unrelated files.
library;

import 'normalize_pairing_key.dart';

const int kPaperTitleKeyMinChars = 20;
const int kPaperTitleKeyMinWords = 3;
const int kPaperTitleKeyMaxChars = 300;

String paperTitleKey(String title) {
  var k = normalizePairingKey(title);
  if (k.length < kPaperTitleKeyMinChars) return '';
  if (k.split(' ').length < kPaperTitleKeyMinWords) return '';
  if (k.length > kPaperTitleKeyMaxChars) k = k.substring(0, kPaperTitleKeyMaxChars).trim();
  return k;
}
