import 'dart:convert';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';
import 'package:sentence_reading/pdf/docx_head.dart';

PdfHeadStyledLine _l(String text, double size, double width) =>
    PdfHeadStyledLine(text: text, sizePt: size, bold: false, y: 0, width: width);

ScannedPdfEntry _e(String name, String role, String title, String doi) => ScannedPdfEntry(
      docUri: 'webdir:d1/$name',
      displayName: name,
      sizeBytes: 1,
      lastModifiedMs: 1,
      advisoryState: PdfAdvisoryState.ready,
      advisoryRole: role,
      advisoryTitle: title,
      advisoryDoi: doi,
    );

List<int> _docx({required String title, required List<String> paras}) {
  final a = Archive();
  final core = '<?xml version="1.0"?><cp:coreProperties xmlns:dc="x">'
      '<dc:title>$title</dc:title></cp:coreProperties>';
  final body = paras
      .map((p) => '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:t xml:space="preserve">$p</w:t></w:r>'
          '<w:r><w:tab/><w:t>.</w:t></w:r></w:p>')
      .join();
  final doc = '<?xml version="1.0"?><w:document><w:body>$body<w:p/></w:body></w:document>';
  a.addFile(ArchiveFile.bytes('docProps/core.xml', utf8.encode(core)));
  a.addFile(ArchiveFile.bytes('word/document.xml', utf8.encode(doc)));
  return ZipEncoder().encode(a);
}

void main() {
  test('design/456 a name list broken over lines is an author line', () {
    expect(looksLikeAuthorLine('Mina Seo Park, Alex W. Brown, Jamie H. Stone, Sang'), isTrue);
    expect(looksLikeAuthorLine('Ouk Lee,* and Hana Lee*'), isTrue);
    expect(looksLikeAuthorLine('Low-Temperature Vapor Deposition Synthesis'), isFalse);
    expect(looksLikeAuthorLine('of Alloyed Nanoparticles with Enhanced Activity'), isFalse);
    expect(looksLikeAuthorLine('Metal Frameworks, Covalent Frameworks, Beyond Catalysis'), isFalse);
  });

  test('design/456 an SI cover whose authors share the title font gives the title', () {
    final g = guessAdvisoryTitle(
      infoTitle: '',
      headText: '',
      displayName: 'x_si.pdf',
      styledLines: [
        _l('Copyright Example Verlag GmbH & Co. KGaA, 12345 Town, Germany, 2016.', 11, 394),
        _l('Supporting Information', 20, 189),
        _l('for Adv. Mater., DOI: 10.1002/adma.201600000', 14, 272),
        _l('Low-Temperature Vapor Deposition Synthesis', 18, 411),
        _l('of Alloyed Nanoparticles with Enhanced Oxygen', 18, 405),
        _l('Reduction Reaction Catalysis', 18, 213),
        _l('Mina Seo Park, Alex W. Brown, Jamie H. Stone, Sang', 18, 442),
        _l('Ouk Lee,* and Hana Lee*', 18, 220),
        _l('Submitted to', 12, 62),
      ],
    );
    expect(
      g.title,
      'Low-Temperature Vapor Deposition Synthesis of Alloyed Nanoparticles '
      'with Enhanced Oxygen Reduction Reaction Catalysis',
    );
  });

  test('design/456 main and SI with different titles but one DOI are a set', () {
    final main = _e('paper.pdf', 'main', 'A Long Enough Paper Title About Catalysts', '10.1002/adma.201600000');
    final si = _e('paper_si.pdf', 'supplementary', 'Copyright Example Verlag GmbH Town Germany', '10.1002/adma.201600000');
    final other = _e('other.pdf', 'main', 'Another Paper Title About Something Else', '10.1002/adma.201699999');
    final built = buildPdfImportListItems([main, si, other]);
    expect(built.nSets, 1);
    final set = built.items.whereType<PdfImportSetItem>().single;
    expect(set.main.docUri, main.docUri);
    expect(set.si.docUri, si.docUri);
    expect(set.si.advisoryTitle, main.advisoryTitle);
    expect(matePresentForEntry(main, [main, si, other]), isTrue);
    expect(matePresentForEntry(other, [main, si, other]), isFalse);
  });

  test('design/456 two mains on one DOI stay single', () {
    final a = _e('a.pdf', 'main', 'First Paper Title About Catalysts Here', '10.1/x.1');
    final b = _e('b.pdf', 'main', 'Second Paper Title About Other Things', '10.1/x.1');
    final s = _e('s.pdf', 'supplementary', 'Supporting Cover Page Words Only Here', '10.1/x.1');
    expect(buildPdfImportListItems([a, b, s]).nSets, 0);
  });

  test('design/456 docx head on the web reads paragraphs and the title', () {
    final h = docxHeadFromBytes(_docx(title: 'Cat &amp; Dog', paras: ['First line', '', 'Second &lt;b&gt;']));
    expect(h.ok, isTrue);
    expect(h.infoTitle, 'Cat & Dog');
    expect(h.headText, 'First line.\n.\nSecond <b>.');
    expect(docxHeadFromBytes(const [1, 2, 3]).ok, isFalse);
  });
}
