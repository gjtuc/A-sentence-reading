/**
 * 무엇을: 본문 Fig./Scheme/Table → 그림 인덱스 매칭 (design/28).
 * 왜: 문장 패널 칩 — 클릭 시에만 figure_index 이동.
 * Python fig_refs.py 와 규칙 동기.
 */
(function (global) {
  "use strict";

  var KIND_NUM =
    /\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?))\b/gi;
  var KIND_ONE =
    /^(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?)/i;

  function stripTags(html) {
    return String(html || "").replace(/<[^>]+>/g, " ");
  }

  function normKey(raw) {
    var m = String(raw || "").match(KIND_ONE);
    if (!m) return null;
    var kindRaw = m[1].toLowerCase();
    var num = m[2].toLowerCase();
    var kind = kindRaw.indexOf("fig") === 0 ? "fig" : kindRaw.indexOf("scheme") === 0 ? "scheme" : "table";
    return kind + ":" + num;
  }

  function parseRefs(text) {
    var plain = stripTags(text);
    var re = new RegExp(KIND_NUM.source, "gi");
    var out = [];
    var seen = Object.create(null);
    var m;
    while ((m = re.exec(plain))) {
      var label = m[1].replace(/\s+/g, " ").trim();
      var key = normKey(label);
      if (!key || seen[key]) continue;
      seen[key] = true;
      out.push(label);
    }
    return out;
  }

  function captionKey(caption) {
    var head = stripTags(caption).trim();
    if (!head) return null;
    var m = head.match(KIND_ONE);
    if (!m) {
      var slice = head.slice(0, 80);
      var re = new RegExp(KIND_NUM.source, "i");
      m = slice.match(re);
      if (!m) return null;
      return normKey(m[1]);
    }
    return normKey(m[0]);
  }

  function matchFigureIndex(figures, refLabel) {
    var want = normKey(refLabel);
    if (!want || !figures || !figures.length) return null;
    for (var i = 0; i < figures.length; i++) {
      var cap = (figures[i] && figures[i].caption) || "";
      if (captionKey(cap) === want) return i;
    }
    return null;
  }

  function hintsForSentence(text, figures) {
    var labels = parseRefs(text);
    var rows = [];
    for (var i = 0; i < labels.length; i++) {
      var idx = matchFigureIndex(figures, labels[i]);
      if (idx == null) continue;
      rows.push({ ref: labels[i], figure_index: idx });
    }
    return rows;
  }

  global.AsrFigRefs = {
    parseRefs: parseRefs,
    captionKey: captionKey,
    matchFigureIndex: matchFigureIndex,
    hintsForSentence: hintsForSentence,
  };
})(typeof window !== "undefined" ? window : globalThis);
