/// design/456 — head text + title of a .docx from its bytes, for the web.
///
/// Same output as the phone's DocxHeadExtract.kt: paragraphs of
/// word/document.xml (`<w:p>`, `<w:t>`) and `<dc:title>` of docProps/core.xml.
library;

import 'dart:convert';

import 'package:archive/archive.dart';

typedef DocxHead = ({bool ok, String headText, String infoTitle, bool truncated, String code});

final _para = RegExp(r'<w:p[\s>][\s\S]*?</w:p>|<w:p/>');
final _text = RegExp(r'<w:t(?:\s[^>]*)?>([\s\S]*?)</w:t>');
final _title = RegExp(r'<dc:title(?:\s[^>]*)?>([\s\S]*?)</dc:title>');
final _entity = RegExp(r'&(#x[0-9a-fA-F]+|#[0-9]+|amp|lt|gt|quot|apos);');

String _unescape(String s) => s.replaceAllMapped(_entity, (m) {
      final e = m[1]!;
      switch (e) {
        case 'amp':
          return '&';
        case 'lt':
          return '<';
        case 'gt':
          return '>';
        case 'quot':
          return '"';
        case 'apos':
          return "'";
      }
      final code = e.startsWith('#x')
          ? int.tryParse(e.substring(2), radix: 16)
          : int.tryParse(e.substring(1));
      return code == null ? m[0]! : String.fromCharCode(code);
    });

DocxHead docxHeadFromBytes(
  List<int> bytes, {
  int maxChars = 8000,
  int maxParagraphs = 40,
}) {
  final Archive zip;
  try {
    zip = ZipDecoder().decodeBytes(bytes);
  } catch (_) {
    return (ok: false, headText: '', infoTitle: '', truncated: false, code: 'not_zip');
  }
  String read(String name) {
    final f = zip.findFile(name);
    if (f == null) return '';
    try {
      return utf8.decode(f.content, allowMalformed: true);
    } catch (_) {
      return '';
    }
  }

  final core = read('docProps/core.xml');
  final title = _unescape(_title.firstMatch(core)?[1] ?? '').trim();
  final doc = read('word/document.xml');
  if (doc.isEmpty && title.isEmpty) {
    return (ok: false, headText: '', infoTitle: '', truncated: false, code: 'no_document');
  }
  final sb = StringBuffer();
  var n = 0;
  var truncated = false;
  for (final p in _para.allMatches(doc)) {
    final t = _unescape(_text.allMatches(p[0]!).map((m) => m[1]!).join()).trim();
    if (t.isEmpty) continue;
    if (sb.isNotEmpty) sb.write('\n');
    sb.write(t);
    n++;
    if (sb.length >= maxChars || n >= maxParagraphs) {
      truncated = sb.length >= maxChars;
      break;
    }
  }
  var head = sb.toString();
  if (head.length > maxChars) head = head.substring(0, maxChars);
  return (ok: true, headText: head.trim(), infoTitle: title, truncated: truncated, code: '');
}
