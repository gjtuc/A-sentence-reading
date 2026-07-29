/**
 * 무엇을: 본문 [n] 각주 ↔ References 매칭 (design/41).
 * 왜: Fig. 칩과 같이 힌트만 — 원문 열기는 /api/cite/resolve.
 * Python cite_refs.py 와 규칙 동기.
 */
(function (global) {
  "use strict";

  var BRACKET =
    /\[(\d+(?:\s*[-–—,]\s*\d+)*(?:\s*,\s*\d+(?:\s*[-–—,]\s*\d+)*)*)\]/g;
  var SUP_NUM = /<sup>\s*(\d{1,3})\s*<\/sup>/gi;

  function stripTags(html) {
    return String(html || "").replace(/<[^>]+>/g, " ");
  }

  function expandToken(token) {
    var out = [];
    var seen = Object.create(null);
    String(token || "")
      .split(/\s*,\s*/)
      .forEach(function (part) {
        part = String(part || "").trim();
        if (!part) return;
        var m = part.match(/^(\d+)\s*[-–—]\s*(\d+)$/);
        if (m) {
          var a = parseInt(m[1], 10);
          var b = parseInt(m[2], 10);
          if (!(a <= b) || b - a > 40) return;
          for (var n = a; n <= b; n++) {
            if (!seen[n] && n >= 1 && n <= 9999) {
              seen[n] = true;
              out.push(n);
            }
          }
          return;
        }
        if (/^\d+$/.test(part)) {
          var v = parseInt(part, 10);
          if (!seen[v] && v >= 1 && v <= 9999) {
            seen[v] = true;
            out.push(v);
          }
        }
      });
    return out;
  }

  function parseCiteNumbers(text) {
    var raw = String(text || "");
    var out = [];
    var seen = Object.create(null);
    function add(nums) {
      (nums || []).forEach(function (n) {
        if (!seen[n]) {
          seen[n] = true;
          out.push(n);
        }
      });
    }
    var plain = stripTags(raw);
    var re = new RegExp(BRACKET.source, "g");
    var m;
    while ((m = re.exec(plain))) {
      add(expandToken(m[1]));
    }
    var reSup = new RegExp(SUP_NUM.source, "gi");
    while ((m = reSup.exec(raw))) {
      add([parseInt(m[1], 10)]);
    }
    return out;
  }

  function lookup(n, bibliography) {
    var list = bibliography || [];
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      if (!e) continue;
      if (parseInt(e.n, 10) === n && String(e.text || "").trim()) {
        return {
          n: n,
          text: String(e.text || ""),
          doi: String(e.doi || ""),
        };
      }
    }
    return null;
  }

  function hintsForSentence(text, bibliography) {
    var nums = parseCiteNumbers(text);
    var rows = [];
    for (var i = 0; i < nums.length; i++) {
      var hit = lookup(nums[i], bibliography);
      if (hit) rows.push(hit);
    }
    return rows;
  }

  global.AsrCiteRefs = {
    parseCiteNumbers: parseCiteNumbers,
    hintsForSentence: hintsForSentence,
    lookup: lookup,
  };
})(typeof window !== "undefined" ? window : globalThis);
