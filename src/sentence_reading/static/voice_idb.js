/**
 * 무엇을: 문장별 목소리 blob IndexedDB 저장.
 * 왜: append-only voice rev의 바이너리 본문 (design/17).
 */
(function (global) {
  "use strict";

  var DB_NAME = "asr-voice-v1";
  var STORE = "blobs";
  var dbp = null;

  function openDb() {
    if (dbp) return dbp;
    dbp = new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE);
        }
      };
      req.onsuccess = function () {
        resolve(req.result);
      };
      req.onerror = function () {
        reject(req.error || new Error("idb_open_failed"));
      };
    });
    return dbp;
  }

  function putBlob(key, blob) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(blob, key);
        tx.oncomplete = function () {
          resolve(key);
        };
        tx.onerror = function () {
          reject(tx.error);
        };
      });
    });
  }

  function getBlob(key) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly");
        var req = tx.objectStore(STORE).get(key);
        req.onsuccess = function () {
          resolve(req.result || null);
        };
        req.onerror = function () {
          reject(req.error);
        };
      });
    });
  }

  global.AsrVoiceIdb = {
    putBlob: putBlob,
    getBlob: getBlob,
  };
})(typeof window !== "undefined" ? window : globalThis);
