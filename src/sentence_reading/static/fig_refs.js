/**
 * 무엇을: 본문 Fig./Scheme/Table → 그림 인덱스 매칭 (design/28).
 * 왜: 문장 패널 칩 — 클릭 시에만 figure_index 이동.
 * design/164 — Figure 6C / 6(C) → base Figure 6 chip.
 * Python fig_refs.py 와 규칙 동기.
 */
(function (global) {
  "use strict";

  var KIND_NUM_LOWER =
    /\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]))\b/g;
  var KIND_NUM_BASE =
    /\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+))\b/gi;
  var KIND_PANEL =
    /\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+)\s*(?:\(([A-Za-z])\)|([A-Z])))\b/gi;

  function stripTags(html) {
    return String(html || "").replace(/<[^>]+>/g, " ");
  }

  function kindToken(kindRaw) {
    var k = String(kindRaw || "").toLowerCase();
    if (k.indexOf("fig") === 0) return "fig";
    if (k.indexOf("scheme") === 0) return "scheme";
    return "table";
  }

  function baseKeyFromNum(kind, num) {
    var lower = String(num || "").toLowerCase();
    var m;
    if (lower.indexOf("s") === 0) {
      m = lower.match(/^s(\d+)/);
      return m ? kind + ":s" + parseInt(m[1], 10) : null;
    }
    m = lower.match(/^(\d+)/);
    return m ? kind + ":" + parseInt(m[1], 10) : null;
  }

  function baseDisplayLabel(kindRaw, num) {
    var k = String(kindRaw || "").toLowerCase();
    if (k.indexOf("fig") === 0) return "Figure " + num;
    if (k.indexOf("scheme") === 0) return "Scheme " + num;
    return "Table " + num;
  }

  function normKey(raw) {
    var s = String(raw || "");
    var m = s.match(/^(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z])/i);
    if (m && m[2] === m[2].toLowerCase()) {
      return kindToken(m[1]) + ":" + m[2].toLowerCase();
    }
    m = s.match(/^(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+)/i);
    if (!m) return null;
    return kindToken(m[1]) + ":" + m[2].toLowerCase();
  }

  function collectKindNumHits(plain) {
    var hits = [];
    var m;
    var reLower = new RegExp(KIND_NUM_LOWER.source, "g");
    while ((m = reLower.exec(plain))) {
      var label = m[1].replace(/\s+/g, " ").trim();
      var key = normKey(label);
      if (key) hits.push({ start: m.index, label: label, key: key });
    }
    var reBase = new RegExp(KIND_NUM_BASE.source, "gi");
    while ((m = reBase.exec(plain))) {
      if (m.index + m[0].length < plain.length) {
        var next = plain.charAt(m.index + m[0].length);
        if (/[A-Za-z]/.test(next)) continue;
      }
      var labelB = m[1].replace(/\s+/g, " ").trim();
      var keyB = normKey(labelB);
      if (keyB) hits.push({ start: m.index, label: labelB, key: keyB });
    }
    return hits;
  }

  function panelParse(full) {
    var inner = String(full || "").match(
      /(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+)\s*(?:\(([A-Za-z])\)|([A-Z]))/i
    );
    if (!inner) return null;
    if (inner[4] && inner[4] !== inner[4].toUpperCase()) return null;
    var kind = kindToken(inner[1]);
    var num = inner[2];
    var baseKey = baseKeyFromNum(kind, num);
    if (!baseKey) return null;
    return { label: baseDisplayLabel(inner[1], num), key: baseKey };
  }

  function panelLabelAndKey(raw) {
    var m = String(raw || "").match(KIND_PANEL);
    if (!m) return null;
    return panelParse(m[1]);
  }

  function matchKeysForLabel(refLabel) {
    var keys = [];
    var panel = panelLabelAndKey(refLabel);
    if (panel && keys.indexOf(panel.key) < 0) keys.push(panel.key);
    var exact = normKey(refLabel);
    if (exact && keys.indexOf(exact) < 0) {
      keys.push(exact);
      var parts = exact.split(":");
      if (parts.length === 2) {
        var base = baseKeyFromNum(parts[0], parts[1]);
        if (base && base !== exact && keys.indexOf(base) < 0) keys.push(base);
      }
    }
    return keys;
  }

  function parseRefs(text) {
    var plain = stripTags(text);
    var hits = collectKindNumHits(plain);
    var m;
    var rePanel = new RegExp(KIND_PANEL.source, "gi");
    while ((m = rePanel.exec(plain))) {
      var parsed = panelParse(m[1]);
      if (parsed) hits.push({ start: m.index, label: parsed.label, key: parsed.key });
    }
    hits.sort(function (a, b) {
      return a.start - b.start;
    });
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < hits.length; i++) {
      if (seen[hits[i].key]) continue;
      seen[hits[i].key] = true;
      out.push(hits[i].label);
    }
    return out;
  }

  function captionKey(caption) {
    var head = stripTags(caption).trim();
    if (!head) return null;
    var m = head.match(KIND_NUM_LOWER) || head.match(KIND_NUM_BASE);
    if (!m) {
      var slice = head.slice(0, 80);
      m = slice.match(KIND_NUM_LOWER) || slice.match(KIND_NUM_BASE);
      if (!m) return null;
    }
    return normKey(m[1]);
  }

  function indexForKey(figures, want) {
    for (var i = 0; i < figures.length; i++) {
      var cap = (figures[i] && figures[i].caption) || "";
      var capKey = captionKey(cap);
      if (capKey === want) return i;
      if (capKey) {
        var parts = capKey.split(":");
        if (parts.length === 2) {
          var base = baseKeyFromNum(parts[0], parts[1]);
          if (base === want) return i;
        }
      }
    }
    return null;
  }

  function matchFigureIndex(figures, refLabel) {
    var keys = matchKeysForLabel(refLabel);
    for (var k = 0; k < keys.length; k++) {
      var idx = indexForKey(figures, keys[k]);
      if (idx != null) return idx;
    }
    return null;
  }

  function hintsForSentence(text, figures) {
    var labels = parseRefs(text);
    var rows = [];
    var seenIdx = Object.create(null);
    for (var i = 0; i < labels.length; i++) {
      var idx = matchFigureIndex(figures, labels[i]);
      if (idx == null || seenIdx[idx]) continue;
      seenIdx[idx] = true;
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
