/**
 * 무엇을: 정속 TTS MP3에 피치 유지 배속 적용.
 * 왜: Cloud 배속 재합성 비용 절감 (design/17) — WSOLA 계열.
 * 구현: HTMLAudioElement.playbackRate + preservesPitch(기본 WSOLA).
 *       Signalsmith WASM은 후속 교체 포인트 (window.AsrStretch).
 */
(function (global) {
  "use strict";

  /**
   * @param {HTMLAudioElement} audio
   * @param {number} rate
   */
  function applyPlaybackRate(audio, rate) {
    if (!audio) return;
    var r = Number(rate);
    if (!(r > 0) || !isFinite(r)) r = 1;
    r = Math.max(0.5, Math.min(2.2, r));
    try {
      // WHY: Chromium/Firefox — preservesPitch=true 시 WSOLA로 피치 유지
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

  global.AsrStretch = {
    applyPlaybackRate: applyPlaybackRate,
  };
})(typeof window !== "undefined" ? window : globalThis);
