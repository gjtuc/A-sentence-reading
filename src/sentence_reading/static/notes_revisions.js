/**
 * 무엇을: 문장별 성찰 노트 append-only 리비전 (localStorage).
 * 왜: 되새김질 — 최신만 기본 표시, 과거는 보관·선택 열람 (design/17).
 * 다음에: (voice blob GCS는 /api/voice/blobs).
 *
 * 스키마 v2:
 * {
 *   version: 2,
 *   papers: {
 *     "<paperKey>": {
 *       "<sentenceId>": {
 *         text: [{ rev, at, body }, ...],
 *         voice: []
 *       }
 *     }
 *   }
 * }
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "asr.notes.v2";
  var LEGACY_KEY = "asr.notes.v1";

  function nowIso() {
    try {
      return new Date().toISOString();
    } catch (_) {
      return String(Date.now());
    }
  }

  function emptyStore() {
    return { version: 2, papers: {} };
  }

  /**
   * v1 { paperKey: { sid: "string" } } → v2.
   * WHY: 기존 단일 문자열을 rev 1 스냅샷으로 승격.
   */
  function migrateV1Object(v1) {
    var out = emptyStore();
    if (!v1 || typeof v1 !== "object") return out;
    Object.keys(v1).forEach(function (pk) {
      var paper = v1[pk];
      if (!paper || typeof paper !== "object") return;
      out.papers[pk] = {};
      Object.keys(paper).forEach(function (sid) {
        var body = paper[sid];
        if (typeof body !== "string" || !body) return;
        out.papers[pk][sid] = {
          text: [{ rev: 1, at: nowIso(), body: body }],
          voice: [],
        };
      });
      if (!Object.keys(out.papers[pk]).length) delete out.papers[pk];
    });
    return out;
  }

  function normalizeEntry(entry) {
    if (!entry || typeof entry !== "object") {
      return { text: [], voice: [] };
    }
    var text = Array.isArray(entry.text) ? entry.text : [];
    var voice = Array.isArray(entry.voice) ? entry.voice : [];
    // v1 잔재: entry 자체가 문자열이었던 경우
    if (typeof entry === "string") {
      return {
        text: entry ? [{ rev: 1, at: nowIso(), body: entry }] : [],
        voice: [],
      };
    }
    return {
      text: text.filter(function (r) {
        return r && typeof r.body === "string" && typeof r.rev === "number";
      }),
      voice: voice,
    };
  }

  function readRaw(storage) {
    storage = storage || global.localStorage;
    if (!storage) return emptyStore();
    try {
      var raw2 = storage.getItem(STORAGE_KEY);
      if (raw2) {
        var data = JSON.parse(raw2);
        if (data && data.version === 2 && data.papers && typeof data.papers === "object") {
          return data;
        }
      }
    } catch (_) {
      /* fall through */
    }
    try {
      var raw1 = storage.getItem(LEGACY_KEY);
      if (raw1) {
        var v1 = JSON.parse(raw1);
        var migrated = migrateV1Object(v1);
        writeRaw(migrated, storage);
        return migrated;
      }
    } catch (_) {
      /* ignore */
    }
    return emptyStore();
  }

  function writeRaw(store, storage) {
    storage = storage || global.localStorage;
    if (!storage) return;
    try {
      storage.setItem(STORAGE_KEY, JSON.stringify(store));
    } catch (_) {
      /* quota */
    }
  }

  function getEntry(store, paperKey, sentenceId) {
    if (!store || !paperKey || !sentenceId) return { text: [], voice: [] };
    var paper = store.papers[paperKey];
    if (!paper || typeof paper !== "object") return { text: [], voice: [] };
    return normalizeEntry(paper[sentenceId]);
  }

  function latestText(store, paperKey, sentenceId) {
    var entry = getEntry(store, paperKey, sentenceId);
    if (!entry.text.length) return "";
    return entry.text[entry.text.length - 1].body || "";
  }

  /**
   * 최신과 다르면 새 rev append. 동일·빈→빈은 no-op.
   * @returns {{ store, appended: boolean, rev: number|null }}
   */
  function appendTextRevision(store, paperKey, sentenceId, body) {
    store = store && store.papers ? store : emptyStore();
    if (!paperKey || !sentenceId) {
      return { store: store, appended: false, rev: null };
    }
    var text = typeof body === "string" ? body : "";
    // WHY: 닫기 제스처 잔여 공백 — trim 후 비교·저장
    var trimmed = text.replace(/\s+$/g, "");
    if (!store.papers[paperKey] || typeof store.papers[paperKey] !== "object") {
      store.papers[paperKey] = {};
    }
    var entry = normalizeEntry(store.papers[paperKey][sentenceId]);
    var prev = entry.text.length ? entry.text[entry.text.length - 1].body : "";
    if (trimmed === prev) {
      store.papers[paperKey][sentenceId] = entry;
      return { store: store, appended: false, rev: entry.text.length ? entry.text[entry.text.length - 1].rev : null };
    }
    // 빈 문자열로 “지우기” — 빈 rev를 쌓지 않고, 이전이 있으면 빈 스냅샷 1회만
    if (!trimmed && !prev) {
      return { store: store, appended: false, rev: null };
    }
    var nextRev = entry.text.length ? entry.text[entry.text.length - 1].rev + 1 : 1;
    entry.text.push({ rev: nextRev, at: nowIso(), body: trimmed });
    store.papers[paperKey][sentenceId] = entry;
    return { store: store, appended: true, rev: nextRev };
  }

  /**
   * 목소리 rev append — blob 은 IndexedDB, 여기엔 메타만.
   * @returns {{ store, appended: boolean, rev: number|null }}
   */
  function appendVoiceRevision(store, paperKey, sentenceId, blobKey, mime) {
    store = store && store.papers ? store : emptyStore();
    if (!paperKey || !sentenceId || !blobKey) {
      return { store: store, appended: false, rev: null };
    }
    if (!store.papers[paperKey] || typeof store.papers[paperKey] !== "object") {
      store.papers[paperKey] = {};
    }
    var entry = normalizeEntry(store.papers[paperKey][sentenceId]);
    var nextRev = entry.voice.length
      ? entry.voice[entry.voice.length - 1].rev + 1
      : 1;
    entry.voice.push({
      rev: nextRev,
      at: nowIso(),
      blobKey: String(blobKey),
      mime: mime || "audio/webm",
    });
    store.papers[paperKey][sentenceId] = entry;
    return { store: store, appended: true, rev: nextRev };
  }

  function latestVoice(store, paperKey, sentenceId) {
    var entry = getEntry(store, paperKey, sentenceId);
    if (!entry.voice.length) return null;
    return entry.voice[entry.voice.length - 1];
  }

  function listTextRevisions(store, paperKey, sentenceId) {
    return getEntry(store, paperKey, sentenceId).text.slice();
  }

  /**
   * 섹션에 속한 문장 id 순서 목록 (state.sentences 기준).
   * section 누락은 "body"로 취급하지 않고 null 키 — 호출측에서 필터.
   */
  function sentenceIdsInSection(sentences, section) {
    if (!Array.isArray(sentences) || section == null || section === "") return [];
    var out = [];
    for (var i = 0; i < sentences.length; i++) {
      var s = sentences[i];
      if (s && s.section === section && s.id) out.push(String(s.id));
    }
    return out;
  }

  function textFp(item) {
    return String(item && item.at != null ? item.at : "") + "\n" + String(item && item.body != null ? item.body : "");
  }

  function voiceFp(item) {
    return (
      String(item && item.at != null ? item.at : "") +
      "\n" +
      String(item && item.blobKey != null ? item.blobKey : "") +
      "\n" +
      String(item && item.mime != null ? item.mime : "")
    );
  }

  /**
   * append-only 병합 — fingerprint 합집합 후 at 정렬·rev 재번호 (서버 notes_gcs 와 동일).
   */
  function mergeRevLists(left, right, kind) {
    var seen = {};
    var out = [];
    function add(seq) {
      if (!Array.isArray(seq)) return;
      for (var i = 0; i < seq.length; i++) {
        var item = seq[i];
        if (!item || typeof item !== "object") continue;
        var fp;
        var copy;
        if (kind === "text") {
          if (typeof item.body !== "string") continue;
          fp = textFp(item);
          copy = { rev: 0, at: String(item.at || ""), body: item.body };
        } else {
          if (!item.blobKey) continue;
          fp = voiceFp(item);
          copy = {
            rev: 0,
            at: String(item.at || ""),
            blobKey: String(item.blobKey),
            mime: String(item.mime || "audio/webm"),
          };
        }
        if (seen[fp]) continue;
        seen[fp] = true;
        out.push(copy);
      }
    }
    add(left);
    add(right);
    out.sort(function (a, b) {
      var aa = a.at || "";
      var bb = b.at || "";
      if (aa < bb) return -1;
      if (aa > bb) return 1;
      return 0;
    });
    for (var j = 0; j < out.length; j++) out[j].rev = j + 1;
    return out;
  }

  function mergeStores(a, b) {
    var sa =
      a && a.papers && typeof a.papers === "object"
        ? a
        : emptyStore();
    var sb =
      b && b.papers && typeof b.papers === "object"
        ? b
        : emptyStore();
    var papers = {};
    var pkeys = {};
    Object.keys(sa.papers || {}).forEach(function (k) {
      pkeys[k] = true;
    });
    Object.keys(sb.papers || {}).forEach(function (k) {
      pkeys[k] = true;
    });
    Object.keys(pkeys).forEach(function (pk) {
      if (!pk) return;
      var pa = sa.papers[pk] && typeof sa.papers[pk] === "object" ? sa.papers[pk] : {};
      var pb = sb.papers[pk] && typeof sb.papers[pk] === "object" ? sb.papers[pk] : {};
      var sids = {};
      Object.keys(pa).forEach(function (s) {
        sids[s] = true;
      });
      Object.keys(pb).forEach(function (s) {
        sids[s] = true;
      });
      var paper = {};
      Object.keys(sids).forEach(function (sid) {
        if (!sid) return;
        var ea = pa[sid] && typeof pa[sid] === "object" ? pa[sid] : {};
        var eb = pb[sid] && typeof pb[sid] === "object" ? pb[sid] : {};
        paper[sid] = {
          text: mergeRevLists(ea.text, eb.text, "text"),
          voice: mergeRevLists(ea.voice, eb.voice, "voice"),
        };
      });
      if (Object.keys(paper).length) papers[pk] = paper;
    });
    return { version: 2, papers: papers };
  }

  global.AsrNotes = {
    STORAGE_KEY: STORAGE_KEY,
    LEGACY_KEY: LEGACY_KEY,
    emptyStore: emptyStore,
    migrateV1Object: migrateV1Object,
    readRaw: readRaw,
    writeRaw: writeRaw,
    getEntry: getEntry,
    latestText: latestText,
    appendTextRevision: appendTextRevision,
    appendVoiceRevision: appendVoiceRevision,
    latestVoice: latestVoice,
    listTextRevisions: listTextRevisions,
    sentenceIdsInSection: sentenceIdsInSection,
    normalizeEntry: normalizeEntry,
    mergeStores: mergeStores,
  };
})(typeof window !== "undefined" ? window : globalThis);
