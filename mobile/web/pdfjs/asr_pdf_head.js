// design/456 - head text, Info.Title and styled head lines of a PDF in the browser.
// Same fields as the phone's PdfHeadExtract.kt (PdfBox), so advisory_title.dart
// reads both the same way. Loaded on demand by web_folder_web.dart.
(function () {
  'use strict';

  var MAX_STYLE_LINES = 80;
  var Y_LINE_TOL = 2.2;
  var BOLD_RE = /bold|black|heavy/i;

  function workerUrl() {
    return new URL('pdfjs/pdf.worker.min.js', document.baseURI).href;
  }

  function fontInfo(page, id) {
    try {
      if (!page.commonObjs.has(id)) return null;
      return page.commonObjs.get(id);
    } catch (_) {
      return null;
    }
  }

  function isBold(page, id, styles) {
    var f = fontInfo(page, id);
    if (f) {
      if (f.bold || f.black) return true;
      if (BOLD_RE.test(String(f.name || ''))) return true;
    }
    var s = styles && styles[id];
    return !!(s && BOLD_RE.test(String(s.fontFamily || '')));
  }

  function pageLines(page, content) {
    var view = page.view;
    var height = view[3] - view[1];
    var items = [];
    for (var i = 0; i < content.items.length; i++) {
      var it = content.items[i];
      if (typeof it.str !== 'string' || it.str.length === 0) continue;
      var t = it.transform;
      var size = Math.hypot(t[2], t[3]) || Math.hypot(t[0], t[1]);
      items.push({
        str: it.str,
        x: t[4],
        y: height - t[5],
        w: it.width || 0,
        size: size,
        bold: isBold(page, it.fontName, content.styles),
      });
    }
    items.sort(function (a, b) { return a.y - b.y || a.x - b.x; });
    var groups = [];
    var cur = null;
    for (var j = 0; j < items.length; j++) {
      var p = items[j];
      if (cur && Math.abs(p.y - cur.y) <= Y_LINE_TOL) {
        cur.items.push(p);
        cur.y = cur.y * 0.7 + p.y * 0.3;
      } else {
        cur = { y: p.y, items: [p] };
        groups.push(cur);
      }
    }
    var out = [];
    for (var g = 0; g < groups.length; g++) {
      var row = groups[g].items.sort(function (a, b) { return a.x - b.x; });
      var text = '';
      var sizes = [];
      var boldN = 0;
      var allN = 0;
      var x0 = Infinity;
      var x1 = -Infinity;
      var prevEnd = null;
      for (var k = 0; k < row.length; k++) {
        var q = row[k];
        if (prevEnd !== null && q.x - prevEnd > q.size * 0.15 &&
            !/\s$/.test(text) && !/^\s/.test(q.str)) {
          text += ' ';
        }
        text += q.str;
        prevEnd = q.x + q.w;
        var n = q.str.replace(/\s/g, '').length;
        for (var c = 0; c < n; c++) {
          if (q.size > 0.5) sizes.push(q.size);
          if (q.bold) boldN++;
          allN++;
        }
        if (n > 0) {
          if (q.x < x0) x0 = q.x;
          if (q.x + q.w > x1) x1 = q.x + q.w;
        }
      }
      text = text.replace(/\s+/g, ' ').trim();
      if (!text || sizes.length === 0) continue;
      sizes.sort(function (a, b) { return a - b; });
      var median = sizes[Math.floor(sizes.length / 2)];
      var minSz = sizes[0];
      var maxSz = sizes[sizes.length - 1];
      out.push({
        text: text,
        size_pt: median,
        bold: boldN * 2 >= allN ? 1 : 0,
        y: groups[g].y,
        mixed_size: maxSz > 0.5 && (maxSz - minSz) / maxSz > 0.18 ? 1 : 0,
        width: x1 > x0 ? x1 - x0 : 0,
      });
    }
    return out;
  }

  function fail(code) {
    return JSON.stringify({
      ok: false, headText: '', infoTitle: '', pageCount: 0,
      truncated: false, code: code, headLines: [],
    });
  }

  // Resolves to a JSON string; never rejects.
  window.asrPdfHead = async function (buffer, maxPages, maxChars) {
    var lib = window.pdfjsLib;
    if (!lib) return fail('no_pdfjs');
    lib.GlobalWorkerOptions.workerSrc = workerUrl();
    var doc = null;
    try {
      doc = await lib.getDocument({
        data: new Uint8Array(buffer),
        isEvalSupported: false,
        disableFontFace: true,
        stopAtErrors: false,
      }).promise;
      var infoTitle = '';
      try {
        var meta = await doc.getMetadata();
        infoTitle = String((meta && meta.info && meta.info.Title) || '').trim();
      } catch (_) {}
      var pages = doc.numPages;
      var end = Math.min(Math.max(maxPages, 1), Math.max(pages, 0));
      var lines = [];
      var head = [];
      for (var i = 1; i <= end; i++) {
        var page = await doc.getPage(i);
        try {
          await page.getOperatorList();
        } catch (_) {}
        var content = await page.getTextContent();
        var pl = pageLines(page, content);
        for (var j = 0; j < pl.length; j++) {
          lines.push(pl[j]);
          head.push(pl[j].text);
        }
        page.cleanup();
      }
      var headText = head.join('\n');
      var truncated = false;
      if (headText.length > maxChars) {
        headText = headText.substring(0, maxChars);
        truncated = true;
      }
      var headLines = lines.slice(0, MAX_STYLE_LINES).map(function (l) {
        if (l.text.length > 500) l.text = l.text.substring(0, 500);
        return l;
      });
      return JSON.stringify({
        ok: true, headText: headText, infoTitle: infoTitle, pageCount: pages,
        truncated: truncated, code: '', headLines: headLines,
      });
    } catch (e) {
      var name = e && e.name ? String(e.name) : '';
      return fail(name === 'PasswordException' ? 'encrypted' : 'parse_fail');
    } finally {
      if (doc) {
        try { await doc.destroy(); } catch (_) {}
      }
    }
  };
})();
