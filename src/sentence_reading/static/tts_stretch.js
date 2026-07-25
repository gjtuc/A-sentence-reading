/**
 * 무엇을: 정속 TTS MP3에 피치 유지 배속 적용.
 * 왜: Cloud 배속 재합성 비용 절감 (design/17) — Signalsmith Stretch (WASM/AudioWorklet).
 * 실패 시: HTMLAudioElement.playbackRate + preservesPitch (브라우저 WSOLA) 폴백.
 *
 * API (window.AsrStretch):
 *   clampRate(n) → number
 *   play({ arrayBuffer, rate, onEnded, onError }) → Promise<{ engine }>
 *   stop()
 *   applyPlaybackRate(audio, rate)  // 레거시·폴백 경로
 */
(function (global) {
  "use strict";

  var RATE_MIN = 0.5;
  var RATE_MAX = 2.2;
  /** |rate-1| 이하면 stretch 생략 (정속 재생). */
  var RATE_EPS = 0.02;

  var playGen = 0;
  var ctx = null;
  var stretchNode = null;
  var htmlAudio = null;
  var objectUrl = null;
  var endTimer = null;
  var lastEngine = "idle";

  /**
   * @param {unknown} rate
   * @returns {number}
   */
  function clampRate(rate) {
    var r = Number(rate);
    // WHY: NaN/±Inf/≤0 은 “말도 안 되는 값” — 정속으로 안전화
    if (!(r > 0) || !isFinite(r)) r = 1;
    if (r < RATE_MIN) r = RATE_MIN;
    if (r > RATE_MAX) r = RATE_MAX;
    return r;
  }

  function clearEndTimer() {
    if (endTimer != null) {
      try {
        clearTimeout(endTimer);
      } catch (_) {
        /* ignore */
      }
      endTimer = null;
    }
  }

  function revokeUrl() {
    if (objectUrl) {
      try {
        URL.revokeObjectURL(objectUrl);
      } catch (_) {
        /* ignore */
      }
      objectUrl = null;
    }
  }

  function stopHtml() {
    if (htmlAudio) {
      try {
        htmlAudio.onended = null;
        htmlAudio.onerror = null;
        htmlAudio.pause();
      } catch (_) {
        /* ignore */
      }
      htmlAudio = null;
    }
    revokeUrl();
  }

  function stopStretch() {
    if (stretchNode) {
      try {
        stretchNode.stop();
      } catch (_) {
        /* ignore */
      }
      try {
        stretchNode.disconnect();
      } catch (_) {
        /* ignore */
      }
      stretchNode = null;
    }
  }

  /** 진행 중 재생 전부 중단 (문장 이동·재클릭). */
  function stop() {
    playGen += 1;
    clearEndTimer();
    stopStretch();
    stopHtml();
    lastEngine = "idle";
  }

  /**
   * @returns {AudioContext}
   */
  function getCtx() {
    var AC = global.AudioContext || global.webkitAudioContext;
    if (!AC) throw new Error("AudioContext unavailable");
    if (!ctx) ctx = new AC();
    return ctx;
  }

  /**
   * @param {HTMLAudioElement} audio
   * @param {number} rate
   */
  function applyPlaybackRate(audio, rate) {
    if (!audio) return;
    var r = clampRate(rate);
    try {
      if ("preservesPitch" in audio) audio.preservesPitch = true;
      if ("mozPreservesPitch" in audio) audio.mozPreservesPitch = true;
      if ("webkitPreservesPitch" in audio) audio.webkitPreservesPitch = true;
    } catch (_) {
      /* ignore */
    }
    try {
      audio.playbackRate = r;
    } catch (_) {
      /* ignore */
    }
  }

  /**
   * @param {ArrayBuffer} arrayBuffer
   * @param {number} rate
   * @param {{ onEnded?: function, onError?: function }} handlers
   * @param {number} gen
   */
  function playViaHtmlAudio(arrayBuffer, rate, handlers, gen) {
    stopHtml();
    var blob = new Blob([arrayBuffer], { type: "audio/mpeg" });
    objectUrl = URL.createObjectURL(blob);
    htmlAudio = new Audio(objectUrl);
    applyPlaybackRate(htmlAudio, rate);
    htmlAudio.onended = function () {
      if (gen !== playGen) return;
      lastEngine = "idle";
      if (handlers && handlers.onEnded) handlers.onEnded();
    };
    htmlAudio.onerror = function () {
      if (gen !== playGen) return;
      lastEngine = "idle";
      if (handlers && handlers.onError) handlers.onError(new Error("html audio play failed"));
    };
    lastEngine = "preservesPitch";
    return htmlAudio.play();
  }

  /**
   * Signalsmith: 버퍼에 정속 샘플 적재 → rate로 시간 스트레치 (semitones=0 → 피치 유지).
   * @param {ArrayBuffer} arrayBuffer
   * @param {number} rate
   * @param {{ onEnded?: function, onError?: function }} handlers
   * @param {number} gen
   */
  function playViaSignalsmith(arrayBuffer, rate, handlers, gen) {
    var factory = global.SignalsmithStretch;
    if (typeof factory !== "function") {
      return Promise.reject(new Error("SignalsmithStretch not loaded"));
    }
    var audioCtx = getCtx();
    return Promise.resolve(audioCtx.resume ? audioCtx.resume() : undefined).then(function () {
      if (gen !== playGen) return;
      // copy — decodeAudioData 는 일부 브라우저에서 버퍼를 detach
      var copy = arrayBuffer.slice(0);
      return audioCtx.decodeAudioData(copy).then(function (audioBuffer) {
        if (gen !== playGen) return;
        if (!audioBuffer || !(audioBuffer.duration > 0)) {
          throw new Error("empty decoded audio");
        }
        var ch = audioBuffer.numberOfChannels || 1;
        if (ch < 1) ch = 1;
        return factory(audioCtx, {
          numberOfInputs: 0,
          numberOfOutputs: 1,
          outputChannelCount: [ch],
        }).then(function (node) {
          if (gen !== playGen) {
            try {
              node.disconnect();
            } catch (_) {
              /* ignore */
            }
            return;
          }
          stopStretch();
          stretchNode = node;
          node.connect(audioCtx.destination);

          var channels = [];
          for (var c = 0; c < ch; c++) {
            // WHY: getChannelData 뷰를 그대로 넘기면 worklet transfer 시 원본 손상 가능 → copy
            channels.push(Float32Array.from(audioBuffer.getChannelData(c)));
          }

          return node.addBuffers(channels).then(function (endSec) {
            if (gen !== playGen) return;
            var inputDur =
              typeof endSec === "number" && endSec > 0 ? endSec : audioBuffer.duration;
            // WHY: 음성 TTS — formant 보정으로 빠른/느린 배속에서 음색 왜곡 완화
            node.schedule({
              active: true,
              input: 0,
              rate: rate,
              semitones: 0,
              formantCompensation: true,
            });
            node.start();
            lastEngine = "signalsmith";

            var ended = false;
            function fireEnded() {
              if (ended || gen !== playGen) return;
              ended = true;
              clearEndTimer();
              lastEngine = "idle";
              if (handlers && handlers.onEnded) handlers.onEnded();
            }

            try {
              node.setUpdateInterval(0.05, function (t) {
                if (gen !== playGen) return;
                if (typeof t === "number" && t >= inputDur - 0.03) fireEnded();
              });
            } catch (_) {
              /* ignore */
            }

            // WHY: updateInterval 누락 대비 — 스트레치된 예상 길이 + 여유
            var ms = Math.ceil((inputDur / rate) * 1000) + 400;
            clearEndTimer();
            endTimer = setTimeout(fireEnded, ms);
          });
        });
      });
    });
  }

  /**
   * @param {{
   *   arrayBuffer: ArrayBuffer,
   *   rate?: number,
   *   onEnded?: function,
   *   onError?: function
   * }} opts
   * @returns {Promise<{ engine: string }>}
   */
  function play(opts) {
    opts = opts || {};
    var buf = opts.arrayBuffer;
    var rate = clampRate(opts.rate);
    var handlers = { onEnded: opts.onEnded, onError: opts.onError };

    stop();
    var gen = playGen;

    if (!buf || !(buf.byteLength > 0)) {
      var errEmpty = new Error("empty audio buffer");
      if (handlers.onError) handlers.onError(errEmpty);
      return Promise.reject(errEmpty);
    }

    // 정속: stretch 불필요 — HTMLAudio가 단순·안정
    if (Math.abs(rate - 1) <= RATE_EPS) {
      return playViaHtmlAudio(buf, 1, handlers, gen).then(function () {
        return { engine: "preservesPitch" };
      });
    }

    var preferSignalsmith =
      typeof global.SignalsmithStretch === "function" &&
      !!(global.AudioContext || global.webkitAudioContext);

    if (preferSignalsmith) {
      return playViaSignalsmith(buf, rate, handlers, gen)
        .then(function () {
          if (gen !== playGen) return { engine: "idle" };
          return { engine: "signalsmith" };
        })
        .catch(function (err) {
          if (gen !== playGen) return { engine: "idle" };
          // WHY: worklet/CORS/decode 실패 시에도 TTS는 들려야 함
          try {
            if (typeof console !== "undefined" && console.warn) {
              console.warn("AsrStretch: Signalsmith failed, fallback to preservesPitch", err);
            }
          } catch (_) {
            /* ignore */
          }
          return playViaHtmlAudio(buf, rate, handlers, gen).then(function () {
            return { engine: "preservesPitch" };
          });
        });
    }

    return playViaHtmlAudio(buf, rate, handlers, gen).then(function () {
      return { engine: "preservesPitch" };
    });
  }

  global.AsrStretch = {
    clampRate: clampRate,
    applyPlaybackRate: applyPlaybackRate,
    play: play,
    stop: stop,
    /** @returns {string} idle | signalsmith | preservesPitch */
    getEngine: function () {
      return lastEngine;
    },
    RATE_MIN: RATE_MIN,
    RATE_MAX: RATE_MAX,
  };
})(typeof window !== "undefined" ? window : globalThis);
