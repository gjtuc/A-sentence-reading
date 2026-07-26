/**
 * 무엇을: 논문별 문장·그림 인덱스 진행 저장 (localStorage).
 * 왜: 새로고침·재열기 후에도 읽던 위치로 (design/05 · design/21).
 * 키 우선: cache:id → hash:sha256 → ses:id (노트 paperKey 와 맞춤).
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
   * @returns {{ figure_index: number, sentence_index: number } | null}
   */
  function loadProgress(paper) {
    var keys = progressKeysFor(paper);
    if (!keys.length) return null;
    var store = readRaw();
    for (var i = 0; i < keys.length; i++) {
      var row = store.papers[keys[i]];
      if (!row || typeof row !== "object") continue;
      return {
        figure_index: Number(row.figure_index) || 0,
        sentence_index: Number(row.sentence_index) || 0,
      };
    }
    return null;
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

  /**
   * 세션 적용 시 저장된 진행으로 인덱스 덮어쓰기 (clamp).
   * @returns {boolean} 복원했는지
   */
  function applyStoredProgress(paper, nFigures, nSentences) {
    if (!paper) return false;
    var prog = loadProgress(paper);
    if (!prog) return false;
    paper.figureIndex = clampIndex(prog.figure_index, nFigures);
    paper.sentenceIndex = clampIndex(prog.sentence_index, nSentences);
    return true;
  }

  global.AsrProgress = {
    get STORAGE_KEY() {
      return STORAGE_KEY;
    },
    setAccountScope: setAccountScope,
    storageKeyForUid: storageKeyForUid,
    emptyStore: emptyStore,
    clampIndex: clampIndex,
    progressKeysFor: progressKeysFor,
    readRaw: readRaw,
    loadProgress: loadProgress,
    saveProgress: saveProgress,
    applyStoredProgress: applyStoredProgress,
  };
})(typeof window !== "undefined" ? window : globalThis);
