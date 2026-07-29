/**
 * 무엇을: 브라우저 Web Speech STT 발음 연습 UI (점수 없음).
 * 왜: design/37 — 원문 vs 인식 diff 만. 서버 STT·AI 채점은 후속.
 * 다음에: 서버 오디오 STT.
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

  /**
   * @param {object} opts
   * @param {() => string} opts.getExpectedPlain
   * @param {(state: object) => void} opts.onUpdate
   */
  function createSttPractice(opts) {
    var recognition = null;
    var active = false;
    var interim = "";
    var finalText = "";

    function emit(extra) {
      if (typeof opts.onUpdate === "function") {
        opts.onUpdate(
          Object.assign(
            {
              supported: !!getRecognitionCtor(),
              active: active,
              interim: interim,
              finalText: finalText,
            },
            extra || {}
          )
        );
      }
    }

    function stop() {
      active = false;
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
      emit({ active: false });
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
          heard: heard || "",
          compare: data,
        });
      } catch (err) {
        emit({
          active: false,
          heard: heard || "",
          compare: { ok: false, error: "compare_failed" },
        });
      }
    }

    function start() {
      var Ctor = getRecognitionCtor();
      if (!Ctor) {
        emit({
          active: false,
          error: "unsupported",
          message: "이 브라우저는 음성 인식을 지원하지 않습니다 (Chrome 권장).",
        });
        return;
      }
      stop();
      interim = "";
      finalText = "";
      recognition = new Ctor();
      recognition.lang = "en-US";
      recognition.interimResults = true;
      recognition.continuous = false;
      active = true;
      emit({ active: true, interim: "", finalText: "", compare: null, error: null });

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
        emit({
          active: true,
          interim: interim,
          finalText: finalText,
        });
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
        if (heard) {
          void compareAndEmit(heard);
        } else {
          emit({ active: false, heard: "", compare: null });
        }
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

    function toggle() {
      if (active) stop();
      else start();
    }

    function reset() {
      stop();
      interim = "";
      finalText = "";
      emit({
        active: false,
        interim: "",
        finalText: "",
        heard: "",
        compare: null,
        error: null,
      });
    }

    return {
      supported: !!getRecognitionCtor(),
      start: start,
      stop: stop,
      toggle: toggle,
      reset: reset,
    };
  }

  /**
   * diff 배열 → HTML (점수 없음).
   * @param {Array<{op:string,expected:?string,heard:?string}>} diff
   */
  function renderDiffHtml(diff) {
    if (!Array.isArray(diff) || !diff.length) {
      return "<span class=\"stt-muted\">비교할 토큰 없음</span>";
    }
    return diff
      .map(function (d) {
        var op = d.op || "";
        if (op === "equal") {
          return (
            "<span class=\"stt-tok stt-equal\">" +
            escapeHtml(d.expected || "") +
            "</span>"
          );
        }
        if (op === "replace") {
          return (
            "<span class=\"stt-tok stt-replace\" title=\"기대: " +
            escapeAttr(d.expected || "") +
            "\">" +
            escapeHtml(d.heard || "") +
            "</span>"
          );
        }
        if (op === "delete") {
          return (
            "<span class=\"stt-tok stt-delete\" title=\"빠짐\">" +
            escapeHtml(d.expected || "") +
            "</span>"
          );
        }
        if (op === "insert") {
          return (
            "<span class=\"stt-tok stt-insert\" title=\"추가됨\">" +
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
