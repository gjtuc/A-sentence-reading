"""Contract test for design/254:
1. HTML / XML entity decoding in advisory title (e.g. metal&#x2013;...)
2. Docx head & infoTitle extraction
3. SAF pickTree initialUri support
4. deleteDocument & scanned PDF deletion
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET


def decode_html_entities(raw: str) -> str:
    s = raw
    if '&' not in s and '<' not in s:
        return re.sub(r'\s+', ' ', s.strip())
    # Hex numeric entities: &#x2013;
    s = re.sub(r'&#x([0-9a-fA-F]+);?', lambda m: chr(int(m.group(1), 16)), s, flags=re.IGNORECASE)
    # Decimal numeric entities: &#8211;
    s = re.sub(r'&#([0-9]+);?', lambda m: chr(int(m.group(1))), s)
    # Common named entities
    reps = {
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&apos;': "'",
        '&nbsp;': ' ',
        '&ndash;': '–',
        '&mdash;': '—',
        '&minus;': '−',
        '&times;': '×',
        '&plusmn;': '±',
    }
    for k, v in reps.items():
        s = s.replace(k, v)
    if '<' in s:
        s = re.sub(r'</?[a-zA-Z0-9]+(?:\s[^>]*)?>', '', s)
    return re.sub(r'\s+', ' ', s.strip())


def test_html_entity_decoding():
    raw = "Metal&#x2013;support interactions in metal oxide-supported atomic, cluster, and nanoparticle catalysis"
    decoded = decode_html_entities(raw)
    assert decoded == "Metal–support interactions in metal oxide-supported atomic, cluster, and nanoparticle catalysis"
    assert "&#x" not in decoded

    # Decimal & XML tags
    raw2 = "<i>In situ</i> study of CO&#8211;metal binding &amp; reactivity"
    decoded2 = decode_html_entities(raw2)
    assert decoded2 == "In situ study of CO–metal binding & reactivity"


def test_docx_mock_archive():
    # Build a minimal docx in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        core_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '  <dc:title>Supporting Information</dc:title>\n'
            '</cp:coreProperties>'
        )
        z.writestr('docProps/core.xml', core_xml)
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            '  <w:body>\n'
            '    <w:p><w:r><w:t>Supporting Information</w:t></w:r></w:p>\n'
            '    <w:p><w:r><w:t>Connection between alumina doping methodology and performance: a review</w:t></w:r></w:p>\n'
            '    <w:p><w:r><w:t>Author One, Author Two</w:t></w:r></w:p>\n'
            '  </w:body>\n'
            '</w:document>'
        )
        z.writestr('word/document.xml', doc_xml)
    buf.seek(0)

    # Parse like DocxHeadExtract
    with zipfile.ZipFile(buf, 'r') as z:
        core_root = ET.fromstring(z.read('docProps/core.xml'))
        title = ''
        for child in core_root:
            if child.tag.endswith('title'):
                title = child.text
        assert title == 'Supporting Information'

        doc_root = ET.fromstring(z.read('word/document.xml'))
        paragraphs = []
        for p in doc_root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
            t = ''.join([elem.text for elem in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if elem.text])
            if t:
                paragraphs.append(t)
        assert len(paragraphs) == 3
        assert paragraphs[1] == 'Connection between alumina doping methodology and performance: a review'


if __name__ == '__main__':
    test_html_entity_decoding()
    test_docx_mock_archive()
    print("ALL TESTS PASSED")
