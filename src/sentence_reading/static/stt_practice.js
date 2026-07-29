/**
 * 무엇을: STT 발음 연습 — 서버 녹음 업로드(38) + 브라우저 Web Speech 폴백(37).
 * 왜: 점수 없이 원문 vs 인식 diff 만. 노트 voice GCS 와 경로 분리.
 * 다음에: 스트리밍 STT · 모드 UI.
 */
(function (global) {
  "use strict";

  function getRecognitionCtor() {
    return (
      global.SpeechRecognition ||
      global.webkitSpeechRecognition ||
      null
    );
  }

  function pickRecorderMime() {
    if (typeof MediaRecorder === "undefined") return "";
    var candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg",
    ];
    for (var i = 0; i < candidates.length; i++) {
      try {
        if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
      } catch (_) {
        /* ignore */
      }
    }
    return "";
  }

  /**
   * @param {object} opts
   * @param {() => string} opts.getExpectedPlain
   * @param {(state: object) => void} opts.onUpdate
   * @param {"server"|"browser"} [opts.mode]
   */
  function createSttPractice(opts) {
    var mode = opts.mode === "browser" ? "browser" : "server";
    var recognition = null;
    var mediaRecorder = null;
    var mediaStream = null;
    var recordChunks = null;
    var active = false;
    var interim = "";
    var finalText = "";
    var uploading = false;

    function emit(extra) {
      if (typeof opts.onUpdate === "function") {
        opts.onUpdate(
          Object.assign(
            {
              mode: mode,
              supported:
                mode === "server"
                  ? typeof MediaRecorder !== "undefined" &&
                    !!(
                      global.navigator &&
                      global.navigator.mediaDevices &&
                      global.navigator.mediaDevices.getUserMedia
                    )
                  : !!getRecognitionCtor(),
              active: active,
              uploading: uploading,
              interim: interim,
              finalText: finalText,
            },
            extra || {}
          )
        );
      }
    }

    function stopBrowserRec() {
      if (recognition) {
        try {
          recognition.onresult = null;
          recognition.onerror = null;
          recognition.onend = null;
          recognition.stop();
        } catch (_) {
          /* ignore */
        }
        recognition = null;
      }
    }

    function stopServerRec(finalize) {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        try {
          if (finalize) mediaRecorder.stop();
          else {
            mediaRecorder.ondataavailable = null;
            mediaRecorder.onstop = null;
            mediaRecorder.stop();
          }
        } catch (_) {
          /* ignore */
        }
      }
      mediaRecorder = null;
      if (mediaStream) {
        try {
          mediaStream.getTracks().forEach(function (t) {
            t.stop();
          });
        } catch (_) {
          /* ignore */
        }
        mediaStream = null;
      }
      if (!finalize) recordChunks = null;
    }

    function stop() {
      active = false;
      stopBrowserRec();
      stopServerRec(false);
      emit({ active: false, uploading: false });
    }

    async function compareAndEmit(heard) {
      var expected =
        typeof opts.getExpectedPlain === "function"
          ? opts.getExpectedPlain() || ""
          : "";
      try {
        var res = await fetch("/api/stt/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ expected: expected, heard: heard || "" }),
        });
        var data = await res.json().catch(function () {
          return {};
        });
        emit({
          active: false,
          uploading: false,
          heard: heard || "",
          compare: data,
        });
      } catch (err) {
        emit({
          active: false,
          uploading: false,
          heard: heard || "",
          compare: { ok: false, error: "compare_failed" },
        });
      }
    }

    async function uploadAndRecognize(blob, mime) {
      uploading = true;
      active = false;
      emit({
        active: false,
        uploading: true,
        message: "서버 인식 중…",
      });
      var expected =
        typeof opts.getExpectedPlain === "function"
          ? opts.getExpectedPlain() || ""
          : "";
      var fd = new FormData();
      var ext = (mime || "").indexOf("mp4") >= 0 ? "m4a" : "webm";
      fd.append("file", blob, "practice." + ext);
      fd.append("expected", expected);
      try {
        var res = await fetch("/api/stt/recognize", {
          method: "POST",
          credentials: "same-origin",
          body: fd,
        });
        var data = await res.json().catch(function () {
          return {};
        });
        uploading = false;
        if (!data || data.ok === false) {
          var err = (data && data.error) || "recognize_failed";
          // WHY: 서버 키 없으면 브라우저 STT 로 한 번 폴백
          if (err === "gemini_unavailable" && getRecognitionCtor()) {
            mode = "browser";
            emit({
              mode: "browser",
              error: null,
              message: "서버 인식 불가 — 브라우저로 전환",
            });
            startBrowser();
            return;
          }
          emit({
            active: false,
            uploading: false,
            error: err,
            message:
              err === "too_large"
                ? "녹음이 너무 큽니다 (최대 2MB)."
                : err === "empty_audio"
                  ? "녹음이 비어 있습니다."
                  : err === "unsupported_mime"
                    ? "지원하지 않는 오디오 형식입니다."
                    : "서버 인식 실패",
          });
          return;
        }
        var heard = data.heard || "";
        if (data.compare) {
          emit({
            active: false,
            uploading: false,
            heard: heard,
            compare: data.compare,
            engine: data.engine || "gemini",
          });
        } else {
          await compareAndEmit(heard);
        }
      } catch (_) {
        uploading = false;
        emit({
          active: false,
          uploading: false,
          error: "recognize_failed",
          message: "서버 인식 요청 실패",
        });
      }
    }

    function startBrowser() {
      var Ctor = getRecognitionCtor();
      if (!Ctor) {
        emit({
          active: false,
          error: "unsupported",
          message: "이 브라우저는 음성 인식을 지원하지 않습니다 (Chrome 권장).",
        });
        return;
      }
      stopBrowserRec();
      interim = "";
      finalText = "";
      recognition = new Ctor();
      recognition.lang = "en-US";
      recognition.interimResults = true;
      recognition.continuous = false;
      active = true;
      emit({
        active: true,
        mode: "browser",
        interim: "",
        finalText: "",
        compare: null,
        error: null,
      });

      recognition.onresult = function (ev) {
        var parts = [];
        var interimParts = [];
        for (var i = 0; i < ev.results.length; i++) {
          var r = ev.results[i];
          var t = (r[0] && r[0].transcript) || "";
          if (r.isFinal) parts.push(t);
          else interimParts.push(t);
        }
        if (parts.length) finalText = parts.join(" ").trim();
        interim = interimParts.join(" ").trim();
        emit({ active: true, interim: interim, finalText: finalText });
      };

      recognition.onerror = function (ev) {
        var code = (ev && ev.error) || "stt_error";
        active = false;
        emit({
          active: false,
          error: code,
          message:
            code === "not-allowed"
              ? "마이크 권한이 필요합니다."
              : code === "no-speech"
                ? "음성이 감지되지 않았습니다."
                : "음성 인식 오류 (" + code + ")",
        });
      };

      recognition.onend = function () {
        active = false;
        var heard = (finalText || interim || "").trim();
        recognition = null;
        if (heard) void compareAndEmit(heard);
        else emit({ active: false, heard: "", compare: null });
      };

      try {
        recognition.start();
      } catch (_) {
        active = false;
        emit({
          active: false,
          error: "start_failed",
          message: "음성 인식을 시작하지 못했습니다.",
        });
      }
    }

    function startServer() {
      if (
        !global.navigator ||
        !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia ||
        typeof MediaRecorder === "undefined"
      ) {
        if (getRecognitionCtor()) {
          mode = "browser";
          startBrowser();
          return;
        }
        emit({
          active: false,
          error: "unsupported",
          message: "이 브라우저는 녹음/인식을 지원하지 않습니다.",
        });
        return;
      }
      stopServerRec(false);
      recordChunks = [];
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(function (stream) {
          mediaStream = stream;
          var mime = pickRecorderMime();
          try {
            mediaRecorder = mime
              ? new MediaRecorder(stream, { mimeType: mime })
              : new MediaRecorder(stream);
          } catch (_) {
            mediaRecorder = new MediaRecorder(stream);
          }
          var usedMime = mediaRecorder.mimeType || mime || "audio/webm";
          mediaRecorder.ondataavailable = function (ev) {
            if (ev.data && ev.data.size > 0) recordChunks.push(ev.data);
          };
          mediaRecorder.onstop = function () {
            var blob = new Blob(recordChunks || [], { type: usedMime });
            recordChunks = null;
            stopServerRec(false);
            if (!blob.size) {
              active = false;
              emit({
                active: false,
                error: "empty_audio",
                message: "녹음이 비어 있습니다.",
              });
              return;
            }
            void uploadAndRecognize(blob, usedMime);
          };
          active = true;
          emit({
            active: true,
            mode: "server",
            uploading: false,
            message: "녹음 중… 다시 누르면 중지·서버 인식",
            compare: null,
            error: null,
          });
          mediaRecorder.start(200);
        })
        .catch(function () {
          active = false;
          if (getRecognitionCtor()) {
            mode = "browser";
            emit({ message: "마이크 녹음 실패 — 브라우저 인식으로 전환" });
            startBrowser();
            return;
          }
          emit({
            active: false,
            error: "not-allowed",
            message: "마이크 권한이 필요합니다.",
          });
        });
    }

    function start() {
      if (uploading) return;
      interim = "";
      finalText = "";
      if (mode === "server") startServer();
      else startBrowser();
    }

    function toggle() {
      if (uploading) return;
      if (active) {
        if (mode === "server" && mediaRecorder) {
          active = false;
          try {
            mediaRecorder.stop();
          } catch (_) {
            stop();
          }
          return;
        }
        stop();
        return;
      }
      start();
    }

    function reset() {
      stop();
      uploading = false;
      interim = "";
      finalText = "";
      emit({
        active: false,
        uploading: false,
        interim: "",
        finalText: "",
        heard: "",
        compare: null,
        error: null,
      });
    }

    function setMode(next) {
      var m = next === "browser" ? "browser" : "server";
      if (m === mode) return;
      reset();
      mode = m;
      emit({ mode: mode });
    }

    return {
      getMode: function () {
        return mode;
      },
      setMode: setMode,
      supported:
        mode === "server"
          ? typeof MediaRecorder !== "undefined"
          : !!getRecognitionCtor(),
      start: start,
      stop: stop,
      toggle: toggle,
      reset: reset,
    };
  }

  function renderDiffHtml(diff) {
    if (!Array.isArray(diff) || !diff.length) {
      return '<span class="stt-muted">비교할 토큰 없음</span>';
    }
    return diff
      .map(function (d) {
        var op = d.op || "";
        if (op === "equal") {
          return (
            '<span class="stt-tok stt-equal">' +
            escapeHtml(d.expected || "") +
            "</span>"
          );
        }
        if (op === "replace") {
          return (
            '<span class="stt-tok stt-replace" title="기대: ' +
            escapeAttr(d.expected || "") +
            '">' +
            escapeHtml(d.heard || "") +
            "</span>"
          );
        }
        if (op === "delete") {
          return (
            '<span class="stt-tok stt-delete" title="빠짐">' +
            escapeHtml(d.expected || "") +
            "</span>"
          );
        }
        if (op === "insert") {
          return (
            '<span class="stt-tok stt-insert" title="추가됨">' +
            escapeHtml(d.heard || "") +
            "</span>"
          );
        }
        return "";
      })
      .join(" ");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  global.AsrSttPractice = {
    create: createSttPractice,
    renderDiffHtml: renderDiffHtml,
    getRecognitionCtor: getRecognitionCtor,
  };
})(typeof window !== "undefined" ? window : globalThis);
