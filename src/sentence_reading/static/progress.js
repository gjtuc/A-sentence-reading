/**
 * 무엇을: 논문별 문장·그림 인덱스 진행 저장 (localStorage).
 * 왜: 새로고침·재열기 후에도 읽던 위치로 (design/05 · design/21 · design/123).
 * 키 우선: cache:id → hash:sha256 → ses:id (노트 paperKey 와 맞춤).
 *
 * design/123: 저장된 인덱스가 범위 밖/비정수면 clamp 하지 않고 거절(fail-closed).
 * 킬스위치: applyStoredProgress({ failClosed: false }) 또는 서버 ASR_PROGRESS_FAIL_CLOSED=0.
 */
(function (global) {
  "use strict";

  var BASE_STORAGE_KEY = "asr.progress.v1";
  var STORAGE_KEY = BASE_STORAGE_KEY;
  var MAX_ENTRIES = 500;
  var _accountUid = null;

  function storageKeyForUid(uid) {
    if (!uid) return BASE_STORAGE_KEY;
    var safe = String(uid).replace(/[^A-Za-z0-9_\-]/g, "").slice(0, 128);
    if (!safe) return BASE_STORAGE_KEY;
    return BASE_STORAGE_KEY + ".u." + safe;
  }

  function setAccountScope(uid) {
    _accountUid = uid ? String(uid) : null;
    STORAGE_KEY = storageKeyForUid(_accountUid);
  }

  function emptyStore() {
    return { version: 1, papers: {} };
  }

  function clampIndex(i, n) {
    if (!n || n < 1) return 0;
    var x = Number(i);
    if (!Number.isFinite(x)) return 0;
    x = Math.floor(x);
    if (x < 0) return 0;
    if (x >= n) return n - 1;
    return x;
  }

  /** Strict int: number whole or decimal-free digit string (no Number("12px")). */
  function isStrictInt(v) {
    if (typeof v === "number") {
      return Number.isFinite(v) && Math.floor(v) === v;
    }
    if (typeof v === "string") {
      var t = v.trim();
      return /^-?\d+$/.test(t);
    }
    return false;
  }

  function toStrictInt(v) {
    if (typeof v === "number") return v;
    return parseInt(String(v).trim(), 10);
  }

  /**
   * WHY: product 4B — refuse open when stored progress cannot be applied exactly.
   * @returns {{ ok: true, sentence_index: number, figure_index: number } |
   *           { ok: false, error: string }}
   */
  function validateProgressIndices(
    sentenceIndex,
    figureIndex,
    sentenceCount,
    figureCount
  ) {
    if (!sentenceCount || sentenceCount < 1) {
      return { ok: false, error: "empty_sentences" };
    }
    if (!isStrictInt(sentenceIndex) || !isStrictInt(figureIndex)) {
      return { ok: false, error: "non_integer_index" };
    }
    var si = toStrictInt(sentenceIndex);
    var fi = toStrictInt(figureIndex);
    if (si < 0 || si >= sentenceCount) {
      return { ok: false, error: "sentence_out_of_range" };
    }
    if (!figureCount || figureCount < 1) {
      if (fi !== 0) {
        return { ok: false, error: "figure_out_of_range" };
      }
    } else if (fi < 0 || fi >= figureCount) {
      return { ok: false, error: "figure_out_of_range" };
    }
    return { ok: true, sentence_index: si, figure_index: fi };
  }

  /**
   * @param {{ cacheId?: string|null, contentHash?: string|null, sessionId?: string|null, id?: string|null }} paper
   * @returns {string[]} 조회·저장 후보 키 (우선순위 순)
   */
  function progressKeysFor(paper) {
    if (!paper) return [];
    var keys = [];
    if (paper.cacheId) keys.push("cache:" + String(paper.cacheId));
    var h = paper.contentHash || paper.content_hash;
    if (h && /^[a-f0-9]{64}$/i.test(String(h))) {
      keys.push("hash:" + String(h).toLowerCase());
    }
    if (paper.sessionId) keys.push("ses:" + String(paper.sessionId));
    else if (paper.id && !paper.cacheId) keys.push("id:" + String(paper.id));
    return keys;
  }

  function readRaw() {
    try {
      var raw = global.localStorage.getItem(STORAGE_KEY);
      if (!raw) return emptyStore();
      var data = JSON.parse(raw);
      if (!data || typeof data !== "object" || data.version !== 1) {
        return emptyStore();
      }
      if (!data.papers || typeof data.papers !== "object") {
        data.papers = {};
      }
      return data;
    } catch (_) {
      return emptyStore();
    }
  }

  function writeRaw(store) {
    try {
      global.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
      return true;
    } catch (_) {
      return false;
    }
  }

  function _evict(papers) {
    var keys = Object.keys(papers);
    if (keys.length <= MAX_ENTRIES) return papers;
    keys.sort(function (a, b) {
      var atA = (papers[a] && papers[a].at) || "";
      var atB = (papers[b] && papers[b].at) || "";
      return atA < atB ? -1 : atA > atB ? 1 : 0;
    });
    var drop = keys.length - MAX_ENTRIES;
    for (var i = 0; i < drop; i++) {
      delete papers[keys[i]];
    }
    return papers;
  }

  /**
   * Raw row without coercing (null = no stored progress).
   * WHY: fail-closed needs original types (string "9", float, etc.).
   */
  function loadProgressRow(paper) {
    var keys = progressKeysFor(paper);
    if (!keys.length) return null;
    var store = readRaw();
    for (var i = 0; i < keys.length; i++) {
      var row = store.papers[keys[i]];
      if (!row || typeof row !== "object") continue;
      if (
        !Object.prototype.hasOwnProperty.call(row, "sentence_index") ||
        !Object.prototype.hasOwnProperty.call(row, "figure_index")
      ) {
        continue;
      }
      return {
        figure_index: row.figure_index,
        sentence_index: row.sentence_index,
        at: row.at || "",
      };
    }
    return null;
  }

  /**
   * @returns {{ figure_index: number, sentence_index: number } | null}
   * Coerced view for callers that only need display numbers (not open gate).
   */
  function loadProgress(paper) {
    var row = loadProgressRow(paper);
    if (!row) return null;
    return {
      figure_index: Number(row.figure_index) || 0,
      sentence_index: Number(row.sentence_index) || 0,
    };
  }

  /**
   * 인덱스를 저장. 후보 키 전부에 같은 값 기록 (cache↔hash 교차 복원).
   */
  function saveProgress(paper, figureIndex, sentenceIndex) {
    var keys = progressKeysFor(paper);
    if (!keys.length) return false;
    var store = readRaw();
    var at;
    try {
      at = new Date().toISOString();
    } catch (_) {
      at = String(Date.now());
    }
    var row = {
      figure_index: Math.max(0, Math.floor(Number(figureIndex) || 0)),
      sentence_index: Math.max(0, Math.floor(Number(sentenceIndex) || 0)),
      at: at,
    };
    for (var i = 0; i < keys.length; i++) {
      store.papers[keys[i]] = row;
    }
    store.papers = _evict(store.papers);
    return writeRaw(store);
  }

  var INVALID_PROGRESS_MSG =
    "저장된 읽기 위치가 이 논문과 맞지 않습니다. 진행을 초기화한 뒤 다시 열어 주세요.";

  /**
   * 세션 적용 시 저장된 진행으로 인덱스 덮어쓰기.
   * design/123: failClosed(default true) → 이상값이면 ok:false (열기 거절).
   * failClosed false → legacy clamp (ASR_PROGRESS_FAIL_CLOSED=0).
   *
   * @returns {{ ok: boolean, restored: boolean, clamped?: boolean, error?: string, message?: string }}
   */
  function applyStoredProgress(paper, nFigures, nSentences, opts) {
    if (!paper) {
      return { ok: true, restored: false };
    }
    var failClosed = !(opts && opts.failClosed === false);
    var row = loadProgressRow(paper);
    if (!row) {
      return { ok: true, restored: false };
    }
    var v = validateProgressIndices(
      row.sentence_index,
      row.figure_index,
      nSentences,
      nFigures
    );
    if (!v.ok) {
      if (!failClosed) {
        // KILL: emergency clamp path — do not use for shared/default.
        paper.figureIndex = clampIndex(row.figure_index, nFigures);
        paper.sentenceIndex = clampIndex(row.sentence_index, nSentences);
        return { ok: true, restored: true, clamped: true, error: v.error };
      }
      // WHY: do not mutate paper indices — caller must refuse open (fail-closed).
      return {
        ok: false,
        restored: false,
        error: v.error,
        message: INVALID_PROGRESS_MSG,
      };
    }
    paper.figureIndex = v.figure_index;
    paper.sentenceIndex = v.sentence_index;
    return { ok: true, restored: true };
  }

  global.AsrProgress = {
    get STORAGE_KEY() {
      return STORAGE_KEY;
    },
    setAccountScope: setAccountScope,
    storageKeyForUid: storageKeyForUid,
    emptyStore: emptyStore,
    clampIndex: clampIndex,
    isStrictInt: isStrictInt,
    validateProgressIndices: validateProgressIndices,
    progressKeysFor: progressKeysFor,
    readRaw: readRaw,
    loadProgress: loadProgress,
    loadProgressRow: loadProgressRow,
    saveProgress: saveProgress,
    applyStoredProgress: applyStoredProgress,
    INVALID_PROGRESS_MSG: INVALID_PROGRESS_MSG,
  };
})(typeof window !== "undefined" ? window : globalThis);
