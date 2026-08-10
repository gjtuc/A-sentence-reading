/**
 * design/82 — shadowing practice mode (separate dialog).
 * Gates: login · kill · opt-in · chunk plan ok before enter.
 * Loop: listen → speak(+2s) → replay → next / 건너뛰기.
 * Live Enable / IPS: ASR out.
 */
(function (global) {
  "use strict";

  var PAD_MS = 2000;
  var api = null;

  function textContent(el, s) {
    if (el) el.textContent = s == null ? "" : String(s);
  }

  function configure(deps) {
    api = deps || null;
  }

  function syncEntryBtn() {
    if (!api || !api.els || !api.els.practiceBtn) return;
    var btn = api.els.practiceBtn;
    var ok =
      !!api.serverAvailable() &&
      !!api.practiceEnabled() &&
      !!api.isLoggedIn() &&
      !!api.cacheId();
    btn.hidden = !api.serverAvailable();
    btn.disabled = !ok;
    btn.title = !api.serverAvailable()
      ? "서버에서 쉐도잉 연습이 꺼져 있습니다."
      : !api.isLoggedIn()
        ? "로그인 후 연습을 사용할 수 있습니다."
        : !api.practiceEnabled()
          ? "Guide에서 쉐도잉 연습을 켜 주세요."
          : !api.cacheId()
            ? "논문을 연 뒤 연습을 시작해 주세요."
            : "쉐도잉 연습 모드";
  }

  async function ensureChunksOrThrow(cacheId) {
    var got = await fetch(
      "/api/shadowing/chunks/" + encodeURIComponent(cacheId),
      { credentials: "same-origin" }
    );
    var data = await got.json().catch(function () {
      return {};
    });
    if (!got.ok) {
      throw new Error(
        (data && data.message) || "연습 구간을 확인하지 못했습니다."
      );
    }
    var plan = data.plan || {};
    if (plan.status === "ok") return plan;
    var built = await fetch(
      "/api/shadowing/chunks/" + encodeURIComponent(cacheId) + "/build",
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ practice_enabled: true }),
      }
    );
    var body = await built.json().catch(function () {
      return {};
    });
    if (!built.ok || !body.ok || !(body.plan && body.plan.status === "ok")) {
      throw new Error(
        (body && body.message) ||
          "연습 구간을 만들지 못했습니다. 다시 시도해 주세요."
      );
    }
    return body.plan;
  }

  function sentenceChunks(plan, sentenceId, plainText) {
    var sentences = (plan && plan.sentences) || {};
    var row = sentences[sentenceId];
    if (row && Array.isArray(row.chunks) && row.chunks.length) {
      return row.chunks.map(String);
    }
    // EDGE: some plans key by index string
    var keys = Object.keys(sentences);
    for (var i = 0; i < keys.length; i++) {
      var r = sentences[keys[i]];
      if (r && Array.isArray(r.chunks) && r.chunks.length) {
        var t = r.text || r.full || "";
        if (!t || t === plainText) return r.chunks.map(String);
      }
    }
    return plainText ? [plainText] : [];
  }

  function createController() {
    var els = (api && api.els) || {};
    var state = {
      open: false,
      busy: false,
      cacheId: null,
      plan: null,
      takes: null,
      sentenceIndex: 0,
      sentenceId: null,
      chunks: [],
      chunkIndex: 0,
      phase: "idle",
      mediaRecorder: null,
      recordChunks: null,
      stream: null,
      localAudio: null,
      objectUrl: null,
      padTimer: null,
    };

    function setStatus(msg, kind) {
      textContent(els.status, msg || "");
      if (els.status) {
        els.status.classList.toggle("is-error", kind === "error");
        els.status.classList.toggle("is-busy", kind === "busy");
      }
    }

    function renderPrompt() {
      var text = state.chunks[state.chunkIndex] || "";
      textContent(els.prompt, text);
      textContent(
        els.meta,
        "문장 " +
          (state.sentenceIndex + 1) +
          " · 구간 " +
          (state.chunkIndex + 1) +
          "/" +
          Math.max(state.chunks.length, 1)
      );
    }

    function stopLocalAudio() {
      if (state.padTimer) {
        clearTimeout(state.padTimer);
        state.padTimer = null;
      }
      if (state.localAudio) {
        try {
          state.localAudio.pause();
        } catch (_) {}
        state.localAudio = null;
      }
      if (state.objectUrl) {
        try {
          URL.revokeObjectURL(state.objectUrl);
        } catch (_) {}
        state.objectUrl = null;
      }
    }

    function stopRecordingTracks() {
      if (state.stream) {
        state.stream.getTracks().forEach(function (t) {
          try {
            t.stop();
          } catch (_) {}
        });
        state.stream = null;
      }
      state.mediaRecorder = null;
      state.recordChunks = null;
    }

    async function playTts(text) {
      stopLocalAudio();
      var res = await fetch("/api/tts", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, speaking_rate: 1 }),
      });
      if (!res.ok) {
        var err = await res.json().catch(function () {
          return {};
        });
        throw new Error((err && err.message) || "듣기를 재생하지 못했습니다.");
      }
      var buf = await res.arrayBuffer();
      var blob = new Blob([buf], { type: "audio/mpeg" });
      var url = URL.createObjectURL(blob);
      state.objectUrl = url;
      var audio = new Audio(url);
      state.localAudio = audio;
      await new Promise(function (resolve, reject) {
        audio.onended = function () {
          resolve();
        };
        audio.onerror = function () {
          reject(new Error("재생 실패"));
        };
        audio.play().catch(reject);
      });
    }

    async function loadTakes() {
      var res = await fetch(
        "/api/shadowing/takes/" + encodeURIComponent(state.cacheId),
        { credentials: "same-origin" }
      );
      var data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        throw new Error((data && data.message) || "연습 기록을 불러오지 못했습니다.");
      }
      state.takes = data.takes || null;
    }

    async function postTake(status, blobKey, mime) {
      var res = await fetch(
        "/api/shadowing/takes/" + encodeURIComponent(state.cacheId),
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            practice_enabled: true,
            action: "take",
            sentence_id: state.sentenceId,
            chunk_index: state.chunkIndex,
            chunk_count: state.chunks.length,
            status: status,
            blob_key: blobKey || null,
            mime: mime || null,
          }),
        }
      );
      var data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok || !data.ok) {
        throw new Error((data && data.message) || "연습 기록을 저장하지 못했습니다.");
      }
      state.takes = data.takes;
    }

    async function uploadBlob(blobKey, blob) {
      if (global.AsrVoiceIdb && AsrVoiceIdb.putBlob) {
        try {
          await AsrVoiceIdb.putBlob(blobKey, blob);
        } catch (_) {}
      }
      var res = await fetch(
        "/api/voice/blobs?key=" + encodeURIComponent(blobKey),
        {
          method: "PUT",
          credentials: "same-origin",
          headers: {
            "Content-Type": blob.type || "application/octet-stream",
          },
          body: blob,
        }
      );
      if (res.status === 401) {
        throw new Error("로그인이 필요합니다.");
      }
      var body = await res.json().catch(function () {
        return {};
      });
      // WHY: fail-closed for practice — do not pretend cloud save when needs_auth/unavailable.
      if (body && body.needs_auth) {
        throw new Error("로그인이 필요합니다.");
      }
      if (res.status === 413 || (body && body.error === "too_large")) {
        throw new Error("녹음이 너무 큽니다.");
      }
      if (!res.ok && body && body.ok === false) {
        throw new Error((body && body.message) || "녹음 업로드에 실패했습니다.");
      }
    }

    function bindSentenceFromReader() {
      var snap = api.readerSnapshot();
      state.sentenceIndex = snap.sentenceIndex || 0;
      state.sentenceId = snap.sentenceId || String(state.sentenceIndex);
      var plain = snap.plainText || "";
      state.chunks = sentenceChunks(state.plan, state.sentenceId, plain);
      if (!state.chunks.length && plain) state.chunks = [plain];
      state.chunkIndex = 0;
      // Resume cursor if same sentence
      var cur = state.takes && state.takes.cursor;
      if (cur && cur.sentence_id === state.sentenceId) {
        var ci = Number(cur.chunk_index) || 0;
        if (ci >= 0 && ci < state.chunks.length) state.chunkIndex = ci;
      }
    }

    async function runListen() {
      state.phase = "listen";
      setStatus("듣는 중…", "busy");
      renderPrompt();
      await playTts(state.chunks[state.chunkIndex] || "");
    }

    async function runSpeak() {
      state.phase = "speak";
      setStatus("같이 말하는 중… (끝난 뒤 2초)", "busy");
      if (
        !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia ||
        typeof MediaRecorder === "undefined"
      ) {
        throw new Error("이 브라우저는 녹음을 지원하지 않습니다.");
      }
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.stream = stream;
      var chunks = [];
      state.recordChunks = chunks;
      var rec = new MediaRecorder(stream);
      state.mediaRecorder = rec;
      rec.ondataavailable = function (ev) {
        if (ev.data && ev.data.size) chunks.push(ev.data);
      };
      var stopped = new Promise(function (resolve) {
        rec.onstop = function () {
          resolve();
        };
      });
      rec.start();
      try {
        await playTts(state.chunks[state.chunkIndex] || "");
      } catch (e) {
        try {
          if (rec.state !== "inactive") rec.stop();
        } catch (_) {}
        stopRecordingTracks();
        throw e;
      }
      await new Promise(function (resolve) {
        state.padTimer = setTimeout(resolve, PAD_MS);
      });
      state.padTimer = null;
      try {
        if (rec.state !== "inactive") rec.stop();
      } catch (_) {}
      await stopped;
      var blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      stopRecordingTracks();
      if (!blob.size) {
        throw new Error("녹음이 비었습니다. 건너뛰기를 사용할 수 있습니다.");
      }
      var blobKey =
        "shadowing|" +
        state.cacheId +
        "|" +
        state.sentenceId +
        "|" +
        state.chunkIndex +
        "|" +
        Date.now();
      await uploadBlob(blobKey, blob);
      await postTake("recorded", blobKey, blob.type || "audio/webm");
      state._lastBlobKey = blobKey;
    }

    async function runReplay() {
      state.phase = "replay";
      setStatus("내 녹음 듣는 중…", "busy");
      var key = state._lastBlobKey;
      if (!key) {
        setStatus("재생할 녹음이 없습니다.", "error");
        return;
      }
      stopLocalAudio();
      var blob = null;
      if (global.AsrVoiceIdb && AsrVoiceIdb.getBlob) {
        try {
          blob = await AsrVoiceIdb.getBlob(key);
        } catch (_) {}
      }
      if (!blob) {
        var res = await fetch(
          "/api/voice/blobs?key=" + encodeURIComponent(key),
          { credentials: "same-origin" }
        );
        if (!res.ok) {
          setStatus("녹음을 불러오지 못했습니다.", "error");
          return;
        }
        blob = await res.blob();
      }
      var url = URL.createObjectURL(blob);
      state.objectUrl = url;
      var audio = new Audio(url);
      state.localAudio = audio;
      await new Promise(function (resolve, reject) {
        audio.onended = resolve;
        audio.onerror = function () {
          reject(new Error("재생 실패"));
        };
        audio.play().catch(reject);
      });
      setStatus("「다음」또는「건너뛰기」를 눌러 주세요.");
      state.phase = "await_next";
    }

    async function advance(skip) {
      if (state.busy) return;
      state.busy = true;
      try {
        if (skip) {
          await postTake("skipped", null, null);
          state._lastBlobKey = null;
        }
        if (state.chunkIndex + 1 < state.chunks.length) {
          state.chunkIndex += 1;
        } else {
          // next sentence in reader order
          var snap = api.readerSnapshot();
          var n = snap.sentenceCount || 0;
          if (state.sentenceIndex + 1 < n) {
            api.goToSentence(state.sentenceIndex + 1);
            bindSentenceFromReader();
          } else {
            setStatus("이 논문 연습을 끝까지 돌았습니다.");
            state.phase = "done";
            renderPrompt();
            return;
          }
        }
        renderPrompt();
        await runListen();
        await runSpeak();
        await runReplay();
      } catch (e) {
        setStatus((e && e.message) || "연습 중 오류", "error");
        state.phase = "await_next";
      } finally {
        state.busy = false;
      }
    }

    async function startLoop() {
      state.busy = true;
      try {
        renderPrompt();
        await runListen();
        await runSpeak();
        await runReplay();
      } catch (e) {
        setStatus((e && e.message) || "연습 중 오류", "error");
        state.phase = "await_next";
      } finally {
        state.busy = false;
      }
    }

    async function open() {
      if (!api) return;
      if (!api.serverAvailable()) {
        setStatus("서버에서 쉐도잉 연습이 꺼져 있습니다.", "error");
        return;
      }
      if (!api.isLoggedIn()) {
        setStatus("로그인 후 연습을 사용할 수 있습니다.", "error");
        return;
      }
      if (!api.practiceEnabled()) {
        setStatus("Guide에서 쉐도잉 연습을 켠 뒤 다시 시도해 주세요.", "error");
        return;
      }
      var cacheId = api.cacheId();
      if (!cacheId) {
        setStatus("논문을 연 뒤 연습을 시작해 주세요.", "error");
        return;
      }
      if (els.dialog && typeof els.dialog.showModal === "function") {
        els.dialog.showModal();
      }
      state.open = true;
      state.cacheId = cacheId;
      setStatus("연습 구간 준비 중…", "busy");
      try {
        // WHY: product B — build must succeed before practice room use.
        state.plan = await ensureChunksOrThrow(cacheId);
        await loadTakes();
        bindSentenceFromReader();
        if (!state.chunks.length) {
          throw new Error("이 문장에 연습 구간이 없습니다.");
        }
        await startLoop();
      } catch (e) {
        setStatus((e && e.message) || "연습을 시작하지 못했습니다.", "error");
      }
    }

    function close() {
      stopLocalAudio();
      try {
        if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
          state.mediaRecorder.stop();
        }
      } catch (_) {}
      stopRecordingTracks();
      state.open = false;
      if (els.dialog && els.dialog.open) {
        try {
          els.dialog.close();
        } catch (_) {}
      }
    }

    async function continueListen() {
      if (!state.cacheId || !api) return;
      setStatus("이어듣기 목록 준비 중…", "busy");
      var snap = api.readerSnapshot();
      var ids = snap.sentenceIds || [];
      var res = await fetch(
        "/api/shadowing/takes/" +
          encodeURIComponent(state.cacheId) +
          "/continue",
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            practice_enabled: true,
            sentence_ids: ids,
          }),
        }
      );
      var data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok || !data.ok) {
        setStatus(
          (data && data.message) || "이어듣기를 준비하지 못했습니다.",
          "error"
        );
        return;
      }
      var playlist = data.playlist || [];
      if (!playlist.length) {
        setStatus(
          "문장 전체를 통과한 녹음이 아직 없습니다. (건너뛴 문장은 제외)",
          "error"
        );
        return;
      }
      // Play first sentence's takes in order (full-pass only).
      for (var s = 0; s < playlist.length; s++) {
        var takes = playlist[s].takes || [];
        for (var i = 0; i < takes.length; i++) {
          var key = takes[i].blob_key;
          if (!key) continue;
          setStatus(
            "이어듣기 · 문장 " + (s + 1) + " · " + (i + 1) + "/" + takes.length,
            "busy"
          );
          var blob = null;
          if (global.AsrVoiceIdb && AsrVoiceIdb.getBlob) {
            try {
              blob = await AsrVoiceIdb.getBlob(key);
            } catch (_) {}
          }
          if (!blob) {
            var r = await fetch(
              "/api/voice/blobs?key=" + encodeURIComponent(key),
              { credentials: "same-origin" }
            );
            if (!r.ok) continue;
            blob = await r.blob();
          }
          stopLocalAudio();
          var url = URL.createObjectURL(blob);
          state.objectUrl = url;
          var audio = new Audio(url);
          state.localAudio = audio;
          await new Promise(function (resolve) {
            audio.onended = resolve;
            audio.onerror = resolve;
            audio.play().catch(resolve);
          });
        }
      }
      setStatus("이어듣기 끝.");
    }

    return {
      open: open,
      close: close,
      next: function () {
        return advance(false);
      },
      skip: function () {
        return advance(true);
      },
      continueListen: continueListen,
      syncEntryBtn: syncEntryBtn,
    };
  }

  var controller = null;

  function boot() {
    if (!api) return;
    controller = createController();
    var els = api.els || {};
    if (els.practiceBtn) {
      els.practiceBtn.addEventListener("click", function () {
        if (els.practiceBtn.disabled) return;
        controller.open();
      });
    }
    if (els.nextBtn) {
      els.nextBtn.addEventListener("click", function () {
        controller.next();
      });
    }
    if (els.skipBtn) {
      els.skipBtn.addEventListener("click", function () {
        controller.skip();
      });
    }
    if (els.continueBtn) {
      els.continueBtn.addEventListener("click", function () {
        controller.continueListen();
      });
    }
    if (els.closeBtn) {
      els.closeBtn.addEventListener("click", function () {
        controller.close();
      });
    }
    syncEntryBtn();
  }

  global.AsrShadowingPractice = {
    configure: configure,
    boot: boot,
    syncEntryBtn: function () {
      syncEntryBtn();
      if (controller) controller.syncEntryBtn();
    },
  };
})(window);
