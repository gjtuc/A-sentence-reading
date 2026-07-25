/**
 * 프론트 네비 + 그림 크롭 + TTS.
 * INVARIANT: figureIndex 와 sentenceIndex 는 서로 갱신하지 않는다.
 * WHY: 접기/펴기·박스 선택 제스처는 제거하고 TTS·크롭을 우선한다.
 */

(() => {
  "use strict";

  const COLLAPSED_PX = 48;
  const SNAP_COLLAPSE_PX = 110;
  const MIN_EXPANDED_PX = 120;
  const DEFAULT_EXPANDED_PX = 340;
  const FIGURE_FOCUS_RATIO = 0.78;
  const FIGURE_LARGE_EPS = 0.9;
  const CHROME_FADE_MS = 400;
  const GROW_MS = 750;
  /** 브라우저 전체화면 ↑/↓ 전환만 약 3× */
  const IMMERSIVE_GROW_MS = 2250;
  const STORAGE_KEY = "asr.figureLayout.v1";
  const MAX_PAPER_TABS = 9;

  let layoutAnimTimer = 0;

  /**
   * 열린 논문 탭 (최대 9). 활성 탭 내용이 state 에 미러링됨.
   * @type {{ id: string, title: string, figures: any[], sentences: any[], figureIndex: number, sentenceIndex: number, sessionId: string | null, source: string, crop: { active: boolean, norm: object | null } }[]}
   */
  let papers = [];
  let activePaperIndex = 0;

  function clearLayoutAnim() {
    if (layoutAnimTimer) {
      window.clearTimeout(layoutAnimTimer);
      layoutAnimTimer = 0;
    }
    document.body.classList.remove(
      "is-figure-growing",
      "is-figure-rising",
      "is-figure-sinking",
      "is-immersive-transition"
    );
    el.layout.classList.remove("is-overflow-clip");
  }

  function setChromeOut(on) {
    document.body.classList.toggle("is-figure-chrome-out", !!on);
  }

  /** 크롬이 사라진 뒤 그림을 채울 높이 (px) */
  function viewportFillHeight() {
    return Math.max(Math.round(el.layout.clientHeight - 16), Math.round(window.innerHeight - 24));
  }

  /** @type {{ figures: any[], sentences: any[], figureIndex: number, sentenceIndex: number, title: string, sessionId: string | null }} */
  const state = {
    figures: [],
    sentences: [],
    figureIndex: 0,
    sentenceIndex: 0,
    title: "",
    sessionId: null,
  };

  /** @type {"boot" | "mock" | "loading" | "ready" | "error"} */
  let uiPhase = "boot";

  /**
   * 그림 전체화면 드래그 크롭 확대.
   * norm: 원본 이미지 대비 0~1 사각형 — ↑글 갔다 ↓그림 돌아와도 유지.
   * @type {{ active: boolean, norm: { x: number, y: number, w: number, h: number } | null }}
   */
  const cropZoom = { active: false, norm: null };

  /** @type {{ mode: "expanded" | "collapsed", heightPx: number, fullscreen: boolean, contentSplit: boolean }} */
  const layout = {
    mode: "expanded",
    heightPx: DEFAULT_EXPANDED_PX,
    fullscreen: false,
    // WHY: 기본은 문장 최소 높이(스크롤 없음) + 나머지 그림
    contentSplit: true,
  };

  const el = {
    layout: document.getElementById("layout"),
    figurePanel: document.getElementById("figurePanel"),
    figureStrip: document.getElementById("figureStrip"),
    figureBody: document.getElementById("figureBody"),
    splitter: document.getElementById("splitter"),
    figureImage: document.getElementById("figureImage"),
    figureCaption: document.getElementById("figureCaption"),
    figureCount: document.getElementById("figureCount"),
    figureCountCollapsed: document.getElementById("figureCountCollapsed"),
    figureViewport: document.getElementById("figureViewport"),
    figureRubberband: document.getElementById("figureRubberband"),
    sentenceText: document.getElementById("sentenceText"),
    sentenceCount: document.getElementById("sentenceCount"),
    sentenceFrame: document.getElementById("sentenceFrame"),
    figureFrame: document.getElementById("figureFrame"),
    stageBadge: document.getElementById("stageBadge"),
    figPrev: document.getElementById("figPrev"),
    figNext: document.getElementById("figNext"),
    sentPrev: document.getElementById("sentPrev"),
    sentNext: document.getElementById("sentNext"),
    pdfInput: document.getElementById("pdfInput"),
    uploadBtn: document.getElementById("uploadBtn"),
    veilBtn: document.getElementById("veilBtn"),
    cacheDeleteBtn: document.getElementById("cacheDeleteBtn"),
    ttsSettingsBtn: document.getElementById("ttsSettingsBtn"),
    ttsDialog: document.getElementById("ttsDialog"),
    ttsForm: document.getElementById("ttsForm"),
    ttsMode: document.getElementById("ttsMode"),
    ttsModeHint: document.getElementById("ttsModeHint"),
    ttsVoiceField: document.getElementById("ttsVoiceField"),
    ttsRateField: document.getElementById("ttsRateField"),
    ttsVoice: document.getElementById("ttsVoice"),
    ttsRate: document.getElementById("ttsRate"),
    ttsRateOut: document.getElementById("ttsRateOut"),
    ttsDialogClose: document.getElementById("ttsDialogClose"),
    ttsPreviewBtn: document.getElementById("ttsPreviewBtn"),
    ttsSampleText: document.getElementById("ttsSampleText"),
    ttsSampleStatus: document.getElementById("ttsSampleStatus"),
    uploadStatus: document.getElementById("uploadStatus"),
    paperTabs: document.getElementById("paperTabs"),
    pomoAlert: document.getElementById("pomoAlert"),
    pomoAlertTime: document.getElementById("pomoAlertTime"),
    pomoBreak: document.getElementById("pomoBreak"),
    pomoBreakLabel: document.getElementById("pomoBreakLabel"),
    pomoBreakTime: document.getElementById("pomoBreakTime"),
    pomoBreakHint: document.getElementById("pomoBreakHint"),
    noteOverlay: document.getElementById("noteOverlay"),
    noteSheet: document.getElementById("noteSheet"),
    noteTextarea: document.getElementById("noteTextarea"),
    noteHistory: document.getElementById("noteHistory"),
    noteHistoryList: document.getElementById("noteHistoryList"),
    noteVoiceBtn: document.getElementById("noteVoiceBtn"),
    noteVoicePlayBtn: document.getElementById("noteVoicePlayBtn"),
    noteVoiceStatus: document.getElementById("noteVoiceStatus"),
    sectionReviewOverlay: document.getElementById("sectionReviewOverlay"),
    sectionReviewSheet: document.getElementById("sectionReviewSheet"),
    sectionReviewTitle: document.getElementById("sectionReviewTitle"),
    sectionReviewHint: document.getElementById("sectionReviewHint"),
    sectionReviewList: document.getElementById("sectionReviewList"),
    sectionReviewContinue: document.getElementById("sectionReviewContinue"),
  };

  // WHY: append-only 리비전 — notes_revisions.js (design/17)
  const AsrNotes = window.AsrNotes;
  const NOTE_ENTER_GAP_MS = 900;
  const NOTE_SAVE_DEBOUNCE_MS = 300;
  /** @type {{ open: boolean, enterStreak: number, lastEnterAt: number, saveTimer: number, boundSentenceId: string | null, draft: string, reviewOpen: boolean, reviewSection: string | null, recording: boolean, mediaRecorder: MediaRecorder | null, recordChunks: Blob[] | null, voiceAudio: HTMLAudioElement | null, voiceObjectUrl: string | null }} */
  const noteUi = {
    open: false,
    enterStreak: 0,
    lastEnterAt: 0,
    saveTimer: 0,
    boundSentenceId: null,
    draft: "",
    reviewOpen: false,
    reviewSection: null,
    recording: false,
    mediaRecorder: null,
    recordChunks: null,
    voiceAudio: null,
    voiceObjectUrl: null,
    voicePlayingKey: null,
  };

  const TTS_STORAGE_KEY = "asr.tts.v2";
  const ttsSettings = {
    mode: "fixed", // fixed | random_normal | random_hard | random_very_hard
    voice: "en-US-Neural2-D",
    speakingRate: 1,
  };
  /** 랜덤 모드 속도 대역 (배속) — 중심 1 / 1.3 / 1.6, 허용폭 ±0.3 */
  const TTS_RATE_BANDS = {
    random_normal: { min: 0.7, max: 1.3 },
    random_hard: { min: 1.0, max: 1.6 },
    random_very_hard: { min: 1.3, max: 1.9 },
  };
  /**
   * 랜덤 모드 locale 가중치 (익숙도 축).
   * WHY: UI에 숫자·지역을 노출하지 않음 — 예측하면 난이도가 깎임.
   */
  const TTS_LOCALE_WEIGHTS = {
    random_normal: { "en-US": 0.8, "en-GB": 0.2 },
    random_hard: { "en-US": 0.4, "en-GB": 0.3, "en-AU": 0.3 },
    random_very_hard: {
      "en-US": 0.2,
      "en-GB": 0.2,
      "en-AU": 0.25,
      "en-IN": 0.35,
    },
  };
  const TTS_RANDOM_MODES = new Set(Object.keys(TTS_RATE_BANDS));
  const TTS_MODES = new Set(["fixed", ...TTS_RANDOM_MODES]);
  /** @type {HTMLAudioElement | null} */
  let ttsAudio = null;
  let ttsObjectUrl = null;
  let ttsFetchGen = 0;

  function clamp(i, n) {
    if (n <= 0) return 0;
    return ((i % n) + n) % n;
  }

  /** object-fit:contain 기준으로 실제 그려진 이미지 박스 (viewport 로컬 좌표) */
  function getContainedImageRect() {
    const vp = el.figureViewport;
    const img = el.figureImage;
    if (!vp || !img || !img.naturalWidth) return null;
    const cw = vp.clientWidth;
    const ch = vp.clientHeight;
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    if (cw < 8 || ch < 8) return null;
    const scale = Math.min(cw / nw, ch / nh);
    const width = nw * scale;
    const height = nh * scale;
    return {
      left: (cw - width) / 2,
      top: (ch - height) / 2,
      width,
      height,
      scale,
      nw,
      nh,
    };
  }

  function clearCropZoomStyles() {
    const img = el.figureImage;
    const vp = el.figureViewport;
    if (vp) vp.classList.remove("is-cropped");
    if (el.figureFrame) el.figureFrame.classList.remove("is-crop-zoomed");
    if (!img) return;
    img.style.left = "";
    img.style.top = "";
    img.style.width = "";
    img.style.height = "";
  }

  function clearCropZoom() {
    cropZoom.active = false;
    cropZoom.norm = null;
    clearCropZoomStyles();
    hideRubberband();
    if (papers.length) snapshotActivePaper();
  }

  function hideRubberband() {
    if (!el.figureRubberband) return;
    el.figureRubberband.hidden = true;
  }

  function setRubberband(x0, y0, x1, y1) {
    const box = el.figureRubberband;
    if (!box) return;
    const left = Math.min(x0, x1);
    const top = Math.min(y0, y1);
    const w = Math.abs(x1 - x0);
    const h = Math.abs(y1 - y0);
    box.hidden = false;
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
    box.style.width = `${w}px`;
    box.style.height = `${h}px`;
  }

  /** norm(0~1) → 뷰포트에 맞게 img 절대 배치. 캡션은 figure-frame 밖(아래) 유지. */
  function applyCropZoom() {
    if (!cropZoom.active || !cropZoom.norm || !layout.fullscreen) {
      clearCropZoomStyles();
      return;
    }
    const vp = el.figureViewport;
    const img = el.figureImage;
    const n = cropZoom.norm;
    if (!vp || !img || !img.naturalWidth) return;

    const vw = vp.clientWidth;
    const vh = vp.clientHeight;
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    const cx = n.x * nw;
    const cy = n.y * nh;
    const cw = Math.max(n.w * nw, 1);
    const ch = Math.max(n.h * nh, 1);
    // 선택 영역이 뷰포트를 최대한 채우도록 (비율 유지)
    const s = Math.min(vw / cw, vh / ch);
    const dispW = nw * s;
    const dispH = nh * s;
    const left = -cx * s + (vw - cw * s) / 2;
    const top = -cy * s + (vh - ch * s) / 2;

    vp.classList.add("is-cropped");
    el.figureFrame.classList.add("is-crop-zoomed");
    img.style.width = `${dispW}px`;
    img.style.height = `${dispH}px`;
    img.style.left = `${left}px`;
    img.style.top = `${top}px`;
  }

  function setCropFromViewportRect(x0, y0, x1, y1) {
    const r = getContainedImageRect();
    if (!r) return false;
    let left = Math.min(x0, x1);
    let top = Math.min(y0, y1);
    let right = Math.max(x0, x1);
    let bottom = Math.max(y0, y1);
    // 이미지 박스 안으로 클램프
    left = Math.max(left, r.left);
    top = Math.max(top, r.top);
    right = Math.min(right, r.left + r.width);
    bottom = Math.min(bottom, r.top + r.height);
    const w = right - left;
    const h = bottom - top;
    if (w < 12 || h < 12) return false;
    cropZoom.norm = {
      x: (left - r.left) / r.width,
      y: (top - r.top) / r.height,
      w: w / r.width,
      h: h / r.height,
    };
    cropZoom.active = true;
    applyCropZoom();
    snapshotActivePaper();
    return true;
  }

  function maxFigureHeight() {
    const layoutH = el.layout.clientHeight || window.innerHeight;
    // 스플리터·문장 최소 여유
    return Math.max(MIN_EXPANDED_PX, layoutH - 160);
  }

  function persistLayout() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          mode: layout.mode,
          heightPx: layout.heightPx,
          contentSplit: layout.contentSplit,
        })
      );
    } catch (_) {
      /* ignore */
    }
  }

  function restoreLayout() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data.mode === "collapsed" || data.mode === "expanded") {
        layout.mode = data.mode;
      }
      if (typeof data.heightPx === "number" && data.heightPx >= MIN_EXPANDED_PX) {
        layout.heightPx = data.heightPx;
      }
      // WHY: 기본 읽기 = 문장 무스크롤 최소 높이. large/immersive 잔상으로
      // contentSplit:false 가 남으면 문장에 스크롤이 생긴다.
      if (layout.mode === "expanded") {
        layout.contentSplit = true;
      } else if (typeof data.contentSplit === "boolean") {
        layout.contentSplit = data.contentSplit;
      }
    } catch (_) {
      /* ignore */
    }
  }

  function applyLayout() {
    const root = document.documentElement;
    const chromeHidden =
      layout.fullscreen || document.body.classList.contains("is-figure-chrome-out");
    document.body.classList.toggle("is-figure-fullscreen", layout.fullscreen);

    const sentenceFocus =
      layout.mode === "collapsed" && !layout.fullscreen && !chromeHidden;
    const defaultSplit =
      layout.mode === "expanded" &&
      layout.contentSplit &&
      !layout.fullscreen &&
      !chromeHidden;

    el.layout.classList.toggle("is-sentence-focus", sentenceFocus);
    el.layout.classList.toggle("is-default-split", defaultSplit);

    if (layout.fullscreen || (chromeHidden && layout.mode === "expanded")) {
      el.layout.classList.remove("is-sentence-focus", "is-default-split");
      el.figurePanel.classList.remove("is-collapsed");
      el.figureStrip.hidden = true;
      const h = Math.max(MIN_EXPANDED_PX, Math.round(layout.heightPx));
      root.style.setProperty("--figure-height", `${h}px`);
      el.splitter.setAttribute("aria-valuenow", layout.fullscreen ? "100" : "90");
      el.figureFrame.setAttribute(
        "title",
        layout.fullscreen
          ? "드래그: 크롭 확대 · Esc: 종료 · 크롭 중 클릭: 축소"
          : "↓ : 그림 전체화면 (크롭)"
      );
      el.splitter.setAttribute("aria-valuemin", "0");
      el.splitter.setAttribute("aria-valuemax", "100");
      return;
    }

    el.figureFrame.setAttribute("title", "↓ : 그림 전체화면 · 전체화면에서 드래그 크롭");

    if (layout.mode === "collapsed") {
      el.figurePanel.classList.add("is-collapsed");
      el.figureStrip.hidden = true;
      root.style.setProperty("--figure-height", `${COLLAPSED_PX}px`);
      el.splitter.setAttribute("aria-valuenow", "0");
    } else if (defaultSplit) {
      el.figurePanel.classList.remove("is-collapsed");
      el.figureStrip.hidden = true;
      root.style.setProperty("--figure-height", "auto");
      el.splitter.setAttribute("aria-valuenow", "50");
    } else {
      el.figurePanel.classList.remove("is-collapsed");
      el.figureStrip.hidden = true;
      const h = Math.min(Math.max(layout.heightPx, MIN_EXPANDED_PX), maxFigureHeight());
      layout.heightPx = h;
      root.style.setProperty("--figure-height", `${h}px`);
      const pct = Math.round((h / maxFigureHeight()) * 100);
      el.splitter.setAttribute("aria-valuenow", String(pct));
    }
    el.splitter.setAttribute("aria-valuemin", "0");
    el.splitter.setAttribute("aria-valuemax", "100");
  }

  function collapse() {
    clearLayoutAnim();
    setChromeOut(false);
    layout.fullscreen = false;
    layout.mode = "collapsed";
    layout.contentSplit = false;
    applyLayout();
    persistLayout();
  }

  function expand(heightPx) {
    clearLayoutAnim();
    setChromeOut(false);
    layout.fullscreen = false;
    layout.mode = "expanded";
    if (typeof heightPx === "number") {
      layout.heightPx = heightPx;
      layout.contentSplit = false;
    } else {
      // 인자 없으면 기본 비율(문장 최소·그림 나머지)로
      layout.contentSplit = true;
    }
    applyLayout();
    persistLayout();
  }

  function enterFigureFullscreen() {
    // WHY: chrome-out 먼저 하면 프레임 크기는 그대로인데 안쪽 그림만 채워짐.
    // 처음부터 전체 높이로 맞춘 뒤 아래에서 올라오게 함.
    if (layout.fullscreen) {
      applyCropZoom();
      return;
    }

    clearLayoutAnim();
    el.layout.classList.add("is-overflow-clip");
    document.body.classList.add("is-figure-rising");

    layout.contentSplit = false;
    layout.mode = "expanded";
    layout.heightPx = viewportFillHeight();
    layout.fullscreen = true;
    setChromeOut(false);
    applyLayout();

    const ms = isBrowserFullscreen() ? IMMERSIVE_GROW_MS : GROW_MS;
    layoutAnimTimer = window.setTimeout(() => {
      document.body.classList.remove("is-figure-rising");
      el.layout.classList.remove("is-overflow-clip");
      applyCropZoom();
      persistLayout();
      layoutAnimTimer = 0;
    }, ms + 40);
  }

  function exitFigureFullscreen() {
    // WHY: 높이만 줄이면 문장이 아직 없어서 그림이 화면 위에서 줄어듦.
    // 올라온 것과 반대로 아래로 내려보낸 뒤 초기 분할로 복귀.
    if (!layout.fullscreen) {
      expand();
      return;
    }

    clearCropZoom();
    clearLayoutAnim();
    el.layout.classList.add("is-overflow-clip");
    document.body.classList.add("is-figure-sinking");

    const ms = isBrowserFullscreen() ? IMMERSIVE_GROW_MS : GROW_MS;
    layoutAnimTimer = window.setTimeout(() => {
      document.body.classList.remove("is-figure-sinking");
      layout.fullscreen = false;
      layout.mode = "expanded";
      layout.contentSplit = true;
      setChromeOut(false);
      applyLayout();
      el.layout.classList.remove("is-overflow-clip");
      persistLayout();
      layoutAnimTimer = 0;
    }, ms);
  }

  function isFigureLarge() {
    if (layout.contentSplit || layout.fullscreen || layout.mode !== "expanded") return false;
    const target = maxFigureHeight() * FIGURE_FOCUS_RATIO;
    return layout.heightPx >= target * FIGURE_LARGE_EPS;
  }

  /**
   * 브라우저 전체화면 전용: 문장 몰입(글만).
   * 대기 없이 즉시 접기 — 글 박스가 펴지는 전환만 ~3× 길게.
   */
  function showImmersiveText() {
    if (!layout.fullscreen && layout.mode === "collapsed") return;

    clearLayoutAnim();
    // WHY: 크롭 확대 상태는 유지 — ↓로 그림 돌아올 때 같은 확대 복원
    clearCropZoomStyles();
    document.body.classList.add("is-immersive-transition");
    el.layout.classList.add("is-overflow-clip");

    layout.fullscreen = false;
    layout.mode = "collapsed";
    layout.heightPx = COLLAPSED_PX;
    layout.contentSplit = false;
    setChromeOut(false);
    applyLayout();

    layoutAnimTimer = window.setTimeout(() => {
      document.body.classList.remove("is-immersive-transition");
      el.layout.classList.remove("is-overflow-clip");
      persistLayout();
      layoutAnimTimer = 0;
    }, IMMERSIVE_GROW_MS);
  }

  /**
   * 브라우저 전체화면 전용: 처음부터 전체 크기인 그림이 아래에서 올라옴.
   */
  function showImmersiveFigure() {
    enterFigureFullscreen();
  }

  /**
   * 키보드 ↑ : 문장 영역 키우기(그림 접기) 토글.
   * WHY: 클릭은 TTS만 — 레이아웃은 키보드로만 (docs/design/15).
   */
  function focusSentence() {
    if (isBrowserFullscreen()) {
      showImmersiveText();
      return;
    }
    if (layout.fullscreen) {
      exitFigureFullscreen();
      return;
    }
    if (layout.mode === "collapsed") {
      expand();
      return;
    }
    collapse();
  }

  /**
   * 키보드 ↓ : 그림 전체화면(크롭용) 토글.
   */
  function focusFigure() {
    if (isBrowserFullscreen()) {
      showImmersiveFigure();
      return;
    }
    if (layout.fullscreen) {
      exitFigureFullscreen();
      return;
    }
    // 글 확대(그림 접힘) 중이면 먼저 기본 분할로
    if (layout.mode === "collapsed") {
      expand();
      return;
    }
    enterFigureFullscreen();
  }

  function advanceFigure(delta) {
    if (!state.figures.length) return;
    clearCropZoom();
    state.figureIndex = clamp(state.figureIndex + delta, state.figures.length);
    render();
    snapshotActivePaper();
  }

  function advanceSentence(delta) {
    if (!state.sentences.length) return;
    if (isSectionReviewOpen()) return;
    stopTts();
    if (noteUi.open) flushNoteSave();
    const prev = state.sentences[state.sentenceIndex];
    const prevSec = prev && prev.section ? String(prev.section) : "";
    const prevIdx = state.sentenceIndex;
    state.sentenceIndex = clamp(
      state.sentenceIndex + delta,
      state.sentences.length
    );
    const next = state.sentences[state.sentenceIndex];
    const nextSec = next && next.section ? String(next.section) : "";
    // WHY: 앞으로 갈 때만 섹션 경계 → 직전 구간 되새김질 (design/17)
    const crossedForward =
      delta > 0 &&
      prevSec &&
      nextSec &&
      prevSec !== nextSec &&
      state.sentenceIndex !== prevIdx;
    render();
    snapshotActivePaper();
    if (crossedForward) {
      openSectionReview(prevSec);
      return;
    }
    if (noteUi.open) {
      loadNoteForCurrentSentence();
      playNoteSentence();
    }
  }

  function figLabel() {
    const nF = state.figures.length;
    return nF ? `Fig ${state.figureIndex + 1} / ${nF}` : "Fig — / —";
  }

  function setUploadStatus(text, kind) {
    el.uploadStatus.textContent = text || "";
    el.uploadStatus.classList.toggle("is-error", kind === "error");
    el.uploadStatus.classList.toggle("is-busy", kind === "busy");
  }

  function setLoading(on) {
    document.body.classList.toggle("is-loading", !!on);
    el.uploadBtn.disabled = !!on;
    el.pdfInput.disabled = !!on;
    if (el.cacheDeleteBtn) el.cacheDeleteBtn.disabled = !!on;
  }

  function updateCacheDeleteBtn() {
    if (!el.cacheDeleteBtn) return;
    const p = papers[activePaperIndex];
    const show = !!(p && !isMockPaper(p) && uiPhase === "ready");
    el.cacheDeleteBtn.hidden = !show;
  }

  function emptyCrop() {
    return { active: false, norm: null };
  }

  function snapshotActivePaper() {
    if (!papers.length || activePaperIndex < 0 || activePaperIndex >= papers.length) {
      return;
    }
    const p = papers[activePaperIndex];
    p.figures = state.figures;
    p.sentences = state.sentences;
    p.figureIndex = state.figureIndex;
    p.sentenceIndex = state.sentenceIndex;
    p.title = state.title;
    p.sessionId = state.sessionId;
    // cacheId / source / isMock 는 탭 메타 — state 에 없으므로 유지
    p.crop = {
      active: !!cropZoom.active,
      norm: cropZoom.norm ? { ...cropZoom.norm } : null,
    };
  }

  function hydrateStateFromPaper(p) {
    state.figures = p.figures || [];
    state.sentences = p.sentences || [];
    state.figureIndex = p.figureIndex || 0;
    state.sentenceIndex = p.sentenceIndex || 0;
    state.title = p.title || "";
    state.sessionId = p.sessionId || null;
    clearCropZoomStyles();
    cropZoom.active = !!(p.crop && p.crop.active && p.crop.norm);
    cropZoom.norm = p.crop && p.crop.norm ? { ...p.crop.norm } : null;
  }

  function stripTags(html) {
    if (!html) return "";
    const d = document.createElement("div");
    d.innerHTML = String(html);
    return (d.textContent || "").trim();
  }

  function shortTitle(title, maxLen) {
    const t = stripTags(title) || "Untitled";
    const n = maxLen || 28;
    return t.length > n ? `${t.slice(0, n - 1)}…` : t;
  }

  function isMockPaper(p) {
    if (!p) return true;
    if (p.isMock) return true;
    const t = String(p.title || "");
    return /^Mock paper/i.test(t) || p.sessionId === "ses_mock";
  }

  function updatePaperTabChrome() {
    const real = realPaperIndices();
    const n = real.length;
    const ord = real.indexOf(activePaperIndex) + 1;
    if (n > 1) {
      el.stageBadge.textContent = `${ord}/${n} · ${shortTitle(state.title, 40)}`;
    } else if (uiPhase === "ready") {
      el.stageBadge.textContent = state.title || "ready";
    } else if (uiPhase === "mock") {
      el.stageBadge.textContent = "";
    }
    updateCacheDeleteBtn();
  }

  function paperTabKey(p, i) {
    if (!p) return `i${i}`;
    return String(p.sessionId || p.cacheId || p.id || `i${i}`);
  }

  function findPaperIndexByKey(key) {
    for (let i = 0; i < papers.length; i++) {
      if (paperTabKey(papers[i], i) === key) return i;
    }
    return -1;
  }

  /**
   * papers[] 인덱스 from → to 로 이동 (탭 줄 순서).
   * WHY: 숫자키·Tab 은 realPaperIndices 순서를 쓰므로 시각 순서와 맞춤.
   */
  function reorderPaper(fromIndex, toIndex) {
    if (fromIndex === toIndex) return false;
    if (fromIndex < 0 || toIndex < 0) return false;
    if (fromIndex >= papers.length || toIndex >= papers.length) return false;
    if (isMockPaper(papers[fromIndex]) || isMockPaper(papers[toIndex])) {
      return false;
    }
    const [item] = papers.splice(fromIndex, 1);
    papers.splice(toIndex, 0, item);
    if (activePaperIndex === fromIndex) {
      activePaperIndex = toIndex;
    } else if (fromIndex < activePaperIndex && toIndex >= activePaperIndex) {
      activePaperIndex -= 1;
    } else if (fromIndex > activePaperIndex && toIndex <= activePaperIndex) {
      activePaperIndex += 1;
    }
    return true;
  }

  /** @type {{ pointerId: number, paperKey: string, startX: number, startY: number, dragging: boolean } | null} */
  let tabDrag = null;
  let suppressTabClickUntil = 0;
  const TAB_DRAG_PX = 6;

  function cssEscapeKey(key) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(key);
    return String(key).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function endTabDrag(ev) {
    if (!tabDrag) return;
    if (ev && ev.pointerId !== tabDrag.pointerId) return;
    const wasDragging = tabDrag.dragging;
    const key = tabDrag.paperKey;
    const pid = tabDrag.pointerId;
    const btn =
      (ev && ev.currentTarget) ||
      (el.paperTabs &&
        el.paperTabs.querySelector(
          `.paper-tab[data-paper-key="${cssEscapeKey(key)}"]`
        ));
    try {
      if (btn && btn.releasePointerCapture) btn.releasePointerCapture(pid);
    } catch (_) {
      /* ignore */
    }
    document.querySelectorAll(".paper-tab.is-dragging").forEach((node) => {
      node.classList.remove("is-dragging");
    });
    tabDrag = null;
    if (wasDragging) {
      suppressTabClickUntil = Date.now() + 400;
      renderPaperTabs();
      updatePaperTabChrome();
      return;
    }
    const idx = findPaperIndexByKey(key);
    if (idx >= 0) activatePaper(idx);
  }

  function onTabPointerMove(ev) {
    if (!tabDrag || ev.pointerId !== tabDrag.pointerId) return;
    const dx = ev.clientX - tabDrag.startX;
    const dy = ev.clientY - tabDrag.startY;
    const btn = ev.currentTarget;
    if (!tabDrag.dragging) {
      if (Math.hypot(dx, dy) < TAB_DRAG_PX) return;
      tabDrag.dragging = true;
      if (btn && btn.classList) btn.classList.add("is-dragging");
      try {
        btn.setPointerCapture(tabDrag.pointerId);
      } catch (_) {
        /* ignore */
      }
    }
    const bar = el.paperTabs;
    if (!bar) return;
    const tabs = [...bar.querySelectorAll(".paper-tab")];
    if (tabs.length < 2) return;
    let hoverSlot = tabs.length - 1;
    for (let t = 0; t < tabs.length; t++) {
      const r = tabs[t].getBoundingClientRect();
      if (ev.clientX < r.left + r.width / 2) {
        hoverSlot = t;
        break;
      }
    }
    const fromIndex = findPaperIndexByKey(tabDrag.paperKey);
    const real = realPaperIndices();
    const fromSlot = real.indexOf(fromIndex);
    if (fromIndex < 0 || fromSlot < 0 || hoverSlot === fromSlot) return;
    const toIndex = real[hoverSlot];
    if (toIndex === undefined) return;
    if (!reorderPaper(fromIndex, toIndex)) return;
    renderPaperTabs();
    updatePaperTabChrome();
    const nextBtn =
      el.paperTabs &&
      el.paperTabs.querySelector(
        `.paper-tab[data-paper-key="${cssEscapeKey(tabDrag.paperKey)}"]`
      );
    if (nextBtn) {
      nextBtn.classList.add("is-dragging");
      try {
        nextBtn.setPointerCapture(tabDrag.pointerId);
      } catch (_) {
        /* ignore */
      }
      wireTabDragPointer(nextBtn);
    }
  }

  function wireTabDragPointer(btn) {
    btn.onpointermove = onTabPointerMove;
    btn.onpointerup = endTabDrag;
    btn.onpointercancel = endTabDrag;
  }

  function renderPaperTabs() {
    const bar = el.paperTabs;
    if (!bar) return;
    const dragSnap = tabDrag ? { ...tabDrag } : null;
    bar.innerHTML = "";
    const real = papers
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => !isMockPaper(p));
    if (real.length <= 1) {
      bar.hidden = true;
      tabDrag = null;
      return;
    }
    bar.hidden = false;
    real.forEach(({ p, i }, slot) => {
      const key = paperTabKey(p, i);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "paper-tab" + (i === activePaperIndex ? " is-active" : "");
      btn.dataset.paperKey = key;
      btn.dataset.paperIndex = String(i);
      btn.title = `${slot + 1}. ${stripTags(p.title) || "Untitled"} (키 ${slot + 1} · 드래그로 순서)`;
      btn.innerHTML = `<span class="paper-tab-num">${slot + 1}</span>${shortTitle(p.title)}`;
      btn.addEventListener("pointerdown", (ev) => {
        if (ev.button !== 0) return;
        tabDrag = {
          pointerId: ev.pointerId,
          paperKey: key,
          startX: ev.clientX,
          startY: ev.clientY,
          dragging: false,
        };
        wireTabDragPointer(btn);
      });
      btn.addEventListener("click", (ev) => {
        if (Date.now() < suppressTabClickUntil) {
          ev.preventDefault();
          ev.stopPropagation();
        }
      });
      if (dragSnap && dragSnap.paperKey === key && dragSnap.dragging) {
        btn.classList.add("is-dragging");
      }
      bar.appendChild(btn);
    });
    if (dragSnap) {
      tabDrag = dragSnap;
      const live = bar.querySelector(
        `.paper-tab[data-paper-key="${cssEscapeKey(dragSnap.paperKey)}"]`
      );
      if (live) wireTabDragPointer(live);
    }
  }

  function realPaperIndices() {
    return papers
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => !isMockPaper(p))
      .map(({ i }) => i);
  }

  function activatePaper(index) {
    if (!papers.length) return;
    const i = clamp(index, papers.length);
    if (isMockPaper(papers[i])) return;
    if (i !== activePaperIndex) {
      stopTts();
      if (noteUi.open) flushNoteSave();
      snapshotActivePaper();
      activePaperIndex = i;
      hydrateStateFromPaper(papers[i]);
      uiPhase = "ready";
      render();
      if (layout.fullscreen) applyCropZoom();
      if (noteUi.open) {
        loadNoteForCurrentSentence();
        playNoteSentence();
      }
    }
    renderPaperTabs();
    const real = realPaperIndices();
    const n = real.length;
    const ord = real.indexOf(activePaperIndex) + 1;
    el.stageBadge.textContent =
      n > 1
        ? `${ord}/${n} · ${shortTitle(state.title, 40)}`
        : state.title || "ready";
    updateCacheDeleteBtn();
  }

  function advancePaper(delta) {
    const real = realPaperIndices();
    if (real.length < 2) return;
    let pos = real.indexOf(activePaperIndex);
    if (pos < 0) pos = 0;
    const next = real[(pos + delta + real.length) % real.length];
    activatePaper(next);
  }

  function applySession(data, phase, opts) {
    const options = opts || {};
    const asNewTab = options.asNewTab !== false && phase !== "mock";
    if (noteUi.open) flushNoteSave();
    const paper = {
      id: data.session_id || `local_${Date.now().toString(36)}`,
      title: data.title || "",
      figures: data.figures || [],
      sentences: data.sentences || [],
      figureIndex: data.figure_index || 0,
      sentenceIndex: data.sentence_index || 0,
      sessionId: data.session_id || null,
      source: data.source || "",
      cacheId: data.cache_id || null,
      isMock: phase === "mock",
      crop: emptyCrop(),
    };

    if (phase === "mock" || !asNewTab) {
      papers = [paper];
      activePaperIndex = 0;
    } else {
      snapshotActivePaper();
      // WHY: mock 은 기본 화면용 — 실제 논문이 열리면 탭에서 제거
      papers = papers.filter((p) => !isMockPaper(p));
      const existing = papers.findIndex(
        (p) => p.sessionId && paper.sessionId && p.sessionId === paper.sessionId
      );
      if (existing >= 0) {
        papers[existing] = paper;
        activePaperIndex = existing;
      } else if (!papers.length) {
        papers = [paper];
        activePaperIndex = 0;
      } else if (papers.length < MAX_PAPER_TABS) {
        papers.push(paper);
        activePaperIndex = papers.length - 1;
      } else {
        const idx = Math.min(activePaperIndex, papers.length - 1);
        papers[idx] = paper;
        activePaperIndex = idx;
      }
    }

    hydrateStateFromPaper(paper);
    clearCropZoom();
    uiPhase = phase;
    render();
    renderPaperTabs();
    const n = papers.filter((p) => !isMockPaper(p)).length;
    if (phase === "mock") {
      el.stageBadge.textContent = "";
    } else if (n > 1) {
      el.stageBadge.textContent = `${activePaperIndex + 1}/${n} · ${shortTitle(state.title, 40)}`;
    } else {
      el.stageBadge.textContent = state.title || phase;
    }
    updateCacheDeleteBtn();
    if (noteUi.open) {
      loadNoteForCurrentSentence();
      playNoteSentence();
    }
  }

  const SECTION_LABELS = {
    title: "Title",
    abstract: "Abstract",
    introduction: "Introduction",
    methods: "Methods",
    experimental: "Experimental",
    results: "Results",
    discussion: "Discussion",
    conclusion: "Conclusion",
    body: "Body",
  };

  function sectionLabel(section) {
    if (!section) return "";
    return SECTION_LABELS[section] || section;
  }

  function setSentenceDisplay(text, isStatus) {
    el.sentenceText.classList.toggle("is-status", !!isStatus);
    if (isStatus) {
      el.sentenceText.textContent = text || "";
    } else {
      // WHY: design/13 — 서버 sanitize된 <sub>/<sup>/<i> 렌더
      el.sentenceText.innerHTML = text || "";
    }
  }

  function render() {
    const nS = state.sentences.length;
    const fig = state.figures.length ? state.figures[state.figureIndex] : null;
    const sent = nS ? state.sentences[state.sentenceIndex] : null;
    const label = figLabel();

    el.figureCount.textContent = label;
    el.figureCountCollapsed.textContent = label;
    const sec = sent ? sectionLabel(sent.section) : "";
    el.sentenceCount.textContent = nS
      ? `Sent ${state.sentenceIndex + 1} / ${nS}${sec ? ` · ${sec}` : ""}`
      : "Sent — / —";

    if (fig) {
      const prevSrc = el.figureImage.getAttribute("src");
      el.figureImage.src = fig.image_src;
      el.figureImage.alt = fig.caption || fig.id;
      el.figureCaption.textContent = fig.caption || "";
      el.figureCaption.hidden = !fig.caption;
      if (prevSrc !== fig.image_src) {
        el.figureImage.addEventListener(
          "load",
          () => {
            if (layout.fullscreen) applyCropZoom();
          },
          { once: true }
        );
      } else if (layout.fullscreen) {
        applyCropZoom();
      }
    } else {
      clearCropZoom();
      el.figureImage.removeAttribute("src");
      el.figureCaption.textContent =
        nS > 0 ? "그림 없음 (embedded 이미지 없음)" : "그림 없음";
      el.figureCaption.hidden = false;
    }

    if (sent) {
      // WHY: 구역은 Sent N/M · Title 배지에만 — 본문 앞 "Title:" 중복 제거
      let body = sent.text || "";
      const lab = sectionLabel(sent.section);
      if (lab) {
        const re = new RegExp(`^${lab}\\s*:\\s*`, "i");
        body = body.replace(re, "");
      }
      setSentenceDisplay(body, false);
    } else if (uiPhase === "loading") {
      setSentenceDisplay(
        "논문을 읽고 있어요.\n잡음을 걸러 읽기 좋게\n다듬는 중이에요.",
        true
      );
    } else if (state.figures.length > 0) {
      setSentenceDisplay(
        "문장 없음\n스캔본이거나 텍스트 추출에\n실패했을 수 있어요.",
        true
      );
    } else {
      setSentenceDisplay(
        "문장이 없습니다.\n파일을 열어 주세요.",
        true
      );
    }
  }

  function currentSentenceId() {
    const sent = state.sentences[state.sentenceIndex];
    return sent && sent.id ? String(sent.id) : null;
  }

  function currentPaperKey() {
    const p = papers[activePaperIndex];
    if (!p) return "orphan";
    if (p.cacheId) return `cache:${p.cacheId}`;
    if (p.sessionId) return `ses:${p.sessionId}`;
    if (p.id) return `id:${p.id}`;
    return "orphan";
  }

  function readNotesStore() {
    if (!AsrNotes) return { version: 2, papers: {} };
    return AsrNotes.readRaw();
  }

  function writeNotesStore(store) {
    if (!AsrNotes) return;
    AsrNotes.writeRaw(store);
  }

  function getNoteText(paperKey, sentenceId) {
    if (!AsrNotes) return "";
    return AsrNotes.latestText(readNotesStore(), paperKey, sentenceId);
  }

  /** 닫기·문장 이동 시에만 append (타이핑 debounce는 draft만). */
  function commitNoteRevision(paperKey, sentenceId, text) {
    if (!AsrNotes || !paperKey || !sentenceId) return;
    var result = AsrNotes.appendTextRevision(
      readNotesStore(),
      paperKey,
      sentenceId,
      text
    );
    writeNotesStore(result.store);
  }

  function flushNoteSave() {
    if (noteUi.saveTimer) {
      window.clearTimeout(noteUi.saveTimer);
      noteUi.saveTimer = 0;
    }
    if (!el.noteTextarea || !noteUi.boundSentenceId) return;
    noteUi.draft = el.noteTextarea.value;
    commitNoteRevision(
      currentPaperKey(),
      noteUi.boundSentenceId,
      noteUi.draft
    );
  }

  function scheduleNoteSave() {
    // WHY: disk append는 닫을 때만 — 여기서는 draft 동기화만
    if (noteUi.saveTimer) window.clearTimeout(noteUi.saveTimer);
    noteUi.saveTimer = window.setTimeout(function () {
      noteUi.saveTimer = 0;
      if (el.noteTextarea) noteUi.draft = el.noteTextarea.value;
    }, NOTE_SAVE_DEBOUNCE_MS);
  }

  function renderNoteHistory(paperKey, sentenceId) {
    if (!el.noteHistoryList || !AsrNotes) return;
    var revs = AsrNotes.listTextRevisions(
      readNotesStore(),
      paperKey,
      sentenceId
    );
    el.noteHistoryList.innerHTML = "";
    if (el.noteHistory) {
      el.noteHistory.hidden = revs.length < 2;
    }
    // 최신 제외, 오래된 것부터 (이전 기록)
    for (var i = 0; i < revs.length - 1; i++) {
      var r = revs[i];
      var li = document.createElement("li");
      li.textContent = "#" + r.rev + " · " + (r.body || "(빈 기록)");
      el.noteHistoryList.appendChild(li);
    }
    updateNoteVoiceButtons(paperKey, sentenceId);
  }

  function updateNoteVoiceButtons(paperKey, sentenceId) {
    if (!el.noteVoicePlayBtn || !AsrNotes) return;
    var latest = AsrNotes.latestVoice(readNotesStore(), paperKey, sentenceId);
    el.noteVoicePlayBtn.hidden = !latest;
  }

  function setNoteVoiceStatus(msg) {
    if (el.noteVoiceStatus) el.noteVoiceStatus.textContent = msg || "";
  }

  /** 사용자 목소리 재생 중단 (노트·분기 리뷰 공통). TTS와 별개. */
  function stopVoicePlayback() {
    if (noteUi.voiceAudio) {
      try {
        noteUi.voiceAudio.onended = null;
        noteUi.voiceAudio.onerror = null;
        noteUi.voiceAudio.pause();
      } catch (_) {
        /* ignore */
      }
      noteUi.voiceAudio = null;
    }
    if (noteUi.voiceObjectUrl) {
      try {
        URL.revokeObjectURL(noteUi.voiceObjectUrl);
      } catch (_) {
        /* ignore */
      }
      noteUi.voiceObjectUrl = null;
    }
    noteUi.voicePlayingKey = null;
  }

  /**
   * IndexedDB blobKey → 최신 한 건만 재생 (이전 재생은 끊음).
   * @param {string} blobKey
   * @param {{ onStatus?: function(string), onMissing?: function() }} opts
   * @returns {Promise<boolean>}
   */
  async function playVoiceBlobKey(blobKey, opts) {
    opts = opts || {};
    if (!blobKey || !window.AsrVoiceIdb) {
      if (opts.onMissing) opts.onMissing();
      return false;
    }
    stopVoicePlayback();
    stopTtsEngineOnly();
    try {
      var blob = await window.AsrVoiceIdb.getBlob(blobKey);
      if (!blob || !(blob.size > 0)) {
        if (opts.onMissing) opts.onMissing();
        return false;
      }
      var url = URL.createObjectURL(blob);
      noteUi.voiceObjectUrl = url;
      var a = new Audio(url);
      noteUi.voiceAudio = a;
      a.onended = function () {
        stopVoicePlayback();
        if (opts.onStatus) opts.onStatus("");
      };
      a.onerror = function () {
        stopVoicePlayback();
        if (opts.onStatus) opts.onStatus("재생 실패");
      };
      await a.play();
      if (opts.onStatus) opts.onStatus("재생 중…");
      return true;
    } catch (_) {
      stopVoicePlayback();
      if (opts.onStatus) opts.onStatus("재생 실패");
      return false;
    }
  }

  async function toggleNoteVoiceRecord() {
    if (!noteUi.boundSentenceId) return;
    if (noteUi.recording) {
      try {
        if (noteUi.mediaRecorder && noteUi.mediaRecorder.state !== "inactive") {
          noteUi.mediaRecorder.stop();
        }
      } catch (_) {
        /* ignore */
      }
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setNoteVoiceStatus("이 브라우저는 녹음을 지원하지 않습니다.");
      return;
    }
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      var chunks = [];
      noteUi.recordChunks = chunks;
      var rec = new MediaRecorder(stream);
      noteUi.mediaRecorder = rec;
      noteUi.recording = true;
      if (el.noteVoiceBtn) el.noteVoiceBtn.textContent = "녹음 중지";
      setNoteVoiceStatus("녹음 중…");
      rec.ondataavailable = function (ev) {
        if (ev.data && ev.data.size) chunks.push(ev.data);
      };
      rec.onstop = async function () {
        noteUi.recording = false;
        if (el.noteVoiceBtn) el.noteVoiceBtn.textContent = "목소리 녹음";
        stream.getTracks().forEach(function (t) {
          try {
            t.stop();
          } catch (_) {
            /* ignore */
          }
        });
        var blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        noteUi.recordChunks = null;
        noteUi.mediaRecorder = null;
        if (!blob.size || !window.AsrVoiceIdb || !AsrNotes) {
          setNoteVoiceStatus("녹음 실패");
          return;
        }
        var pk = currentPaperKey();
        var sid = noteUi.boundSentenceId;
        var blobKey = pk + "|" + sid + "|" + Date.now();
        try {
          await window.AsrVoiceIdb.putBlob(blobKey, blob);
          var result = AsrNotes.appendVoiceRevision(
            readNotesStore(),
            pk,
            sid,
            blobKey,
            blob.type || "audio/webm"
          );
          writeNotesStore(result.store);
          setNoteVoiceStatus("저장됨 · rev " + result.rev);
          updateNoteVoiceButtons(pk, sid);
        } catch (err) {
          setNoteVoiceStatus("저장 실패");
        }
      };
      rec.start();
    } catch (err) {
      noteUi.recording = false;
      setNoteVoiceStatus("마이크 권한이 필요합니다.");
    }
  }

  async function playLatestNoteVoice() {
    if (!noteUi.boundSentenceId || !AsrNotes) return;
    var latest = AsrNotes.latestVoice(
      readNotesStore(),
      currentPaperKey(),
      noteUi.boundSentenceId
    );
    if (!latest) return;
    await playVoiceBlobKey(latest.blobKey, {
      onStatus: setNoteVoiceStatus,
      onMissing: function () {
        setNoteVoiceStatus("파일을 찾을 수 없습니다.");
      },
    });
  }

  function loadNoteForCurrentSentence() {
    if (!el.noteTextarea) return;
    var sid = currentSentenceId();
    noteUi.boundSentenceId = sid;
    noteUi.enterStreak = 0;
    noteUi.lastEnterAt = 0;
    var pk = currentPaperKey();
    var latest = sid ? getNoteText(pk, sid) : "";
    noteUi.draft = latest;
    el.noteTextarea.value = latest;
    renderNoteHistory(pk, sid);
  }

  function isNoteOpen() {
    return !!(noteUi.open && el.noteOverlay && !el.noteOverlay.hidden);
  }

  function isSectionReviewOpen() {
    return !!(
      noteUi.reviewOpen &&
      el.sectionReviewOverlay &&
      !el.sectionReviewOverlay.hidden
    );
  }

  function playNoteSentence() {
    // WHY: 노트는 듣고 적기 — 문장 텍스트 대신 TTS
    speakCurrentSentence();
  }

  function openNoteOverlay() {
    if (!el.noteOverlay || !el.noteTextarea) return;
    if (el.ttsDialog && el.ttsDialog.open) return;
    if (isSectionReviewOpen()) closeSectionReview({ resume: false });
    stopTts();
    noteUi.open = true;
    el.noteOverlay.hidden = false;
    document.body.classList.add("is-note-open");
    if (el.noteOverlay.scrollTop) el.noteOverlay.scrollTop = 0;
    loadNoteForCurrentSentence();
    playNoteSentence();
    lockEscapeWhileNoteInFs();
    window.setTimeout(function () {
      el.noteTextarea.focus();
      var len = el.noteTextarea.value.length;
      try {
        el.noteTextarea.setSelectionRange(len, len);
      } catch (_) {
        /* ignore */
      }
    }, 0);
  }

  function closeNoteOverlay() {
    if (!el.noteOverlay) return;
    flushNoteSave();
    stopTts();
    noteUi.open = false;
    noteUi.enterStreak = 0;
    noteUi.lastEnterAt = 0;
    noteUi.boundSentenceId = null;
    noteUi.draft = "";
    el.noteOverlay.hidden = true;
    document.body.classList.remove("is-note-open");
    unlockEscapeKeys();
  }

  function plainSentencePreview(sent) {
    if (!sent) return "";
    var body = String(sent.text || "");
    var lab = sectionLabel(sent.section);
    if (lab) {
      var re = new RegExp("^" + lab + "\\s*:\\s*", "i");
      body = body.replace(re, "");
    }
    return plainSentenceText(body).slice(0, 120);
  }

  function openSectionReview(section) {
    if (!el.sectionReviewOverlay || !el.sectionReviewList || !AsrNotes) return;
    if (noteUi.open) closeNoteOverlay();
    stopTts();
    stopVoicePlayback();
    noteUi.reviewOpen = true;
    noteUi.reviewSection = section;
    el.sectionReviewOverlay.hidden = false;
    document.body.classList.add("is-section-review");
    var label = sectionLabel(section) || section;
    if (el.sectionReviewTitle) {
      el.sectionReviewTitle.textContent = label + " · 되새김질";
    }
    var ids = AsrNotes.sentenceIdsInSection(state.sentences, section);
    var pk = currentPaperKey();
    var store = readNotesStore();
    el.sectionReviewList.innerHTML = "";
    if (!ids.length) {
      var empty = document.createElement("li");
      empty.className = "section-review-item-body is-empty";
      empty.textContent = "이 구간에 문장이 없습니다.";
      el.sectionReviewList.appendChild(empty);
    }
    ids.forEach(function (sid) {
      var sent = null;
      for (var i = 0; i < state.sentences.length; i++) {
        if (state.sentences[i] && String(state.sentences[i].id) === sid) {
          sent = state.sentences[i];
          break;
        }
      }
      var latest = AsrNotes.latestText(store, pk, sid);
      var voice = AsrNotes.latestVoice(store, pk, sid);
      var revs = AsrNotes.listTextRevisions(store, pk, sid);
      var li = document.createElement("li");
      li.className = "section-review-row";

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "section-review-item";
      btn.dataset.sentenceId = sid;
      var meta = document.createElement("span");
      meta.className = "section-review-item-meta";
      meta.textContent =
        "rev " +
        (revs.length ? revs[revs.length - 1].rev : 0) +
        (voice ? " · 목소리 #" + voice.rev : "") +
        " · " +
        (plainSentencePreview(sent) || sid);
      var body = document.createElement("span");
      body.className =
        "section-review-item-body" + (latest ? "" : " is-empty");
      body.textContent = latest || "(아직 기록 없음 — 눌러서 쓰기)";
      btn.appendChild(meta);
      btn.appendChild(body);
      btn.addEventListener("click", function () {
        onSectionReviewPick(sid);
      });
      li.appendChild(btn);

      // WHY: 목소리 버튼은 인덱스 변경 없음 — 문장 선택(텍스트 버튼)과 분리 (INVARIANT)
      if (voice && voice.blobKey) {
        var playBtn = document.createElement("button");
        playBtn.type = "button";
        playBtn.className = "section-review-voice-btn";
        playBtn.dataset.sentenceId = sid;
        playBtn.dataset.blobKey = voice.blobKey;
        playBtn.title = "최신 목소리 듣기 (rev " + voice.rev + ")";
        playBtn.setAttribute("aria-label", "최신 목소리 듣기");
        playBtn.textContent = "▶ 목소리";
        playBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          onSectionReviewPlayVoice(sid, voice.blobKey, playBtn);
        });
        li.appendChild(playBtn);
      }

      el.sectionReviewList.appendChild(li);
    });
    if (el.sectionReviewSheet) {
      window.setTimeout(function () {
        el.sectionReviewSheet.focus();
      }, 0);
    }
  }

  /**
   * 분기 리뷰에서 최신 목소리만 재생/중지 — sentence_index 불변.
   * @param {string} sentenceId
   * @param {string} blobKey
   * @param {HTMLButtonElement} playBtn
   */
  async function onSectionReviewPlayVoice(sentenceId, blobKey, playBtn) {
    if (!blobKey) return;
    // 같은 키 재생 중이면 토글로 중지
    if (
      noteUi.voiceAudio &&
      noteUi.voicePlayingKey === blobKey &&
      !noteUi.voiceAudio.paused
    ) {
      stopVoicePlayback();
      if (playBtn) playBtn.textContent = "▶ 목소리";
      return;
    }
    if (playBtn) {
      playBtn.disabled = true;
      playBtn.textContent = "…";
    }
    noteUi.voicePlayingKey = blobKey;
    var ok = await playVoiceBlobKey(blobKey, {
      onStatus: function (msg) {
        if (!playBtn) return;
        if (msg === "재생 중…") playBtn.textContent = "■ 중지";
        else if (msg === "재생 실패") playBtn.textContent = "실패";
        else playBtn.textContent = "▶ 목소리";
      },
      onMissing: function () {
        if (playBtn) playBtn.textContent = "없음";
      },
    });
    if (playBtn) {
      playBtn.disabled = false;
      if (!ok && playBtn.textContent === "…") playBtn.textContent = "▶ 목소리";
    }
    void sentenceId;
  }

  function closeSectionReview(opts) {
    opts = opts || {};
    if (!el.sectionReviewOverlay) return;
    stopVoicePlayback();
    noteUi.reviewOpen = false;
    noteUi.reviewSection = null;
    el.sectionReviewOverlay.hidden = true;
    document.body.classList.remove("is-section-review");
    if (opts.resume !== false && noteUi.open) {
      loadNoteForCurrentSentence();
    }
  }

  function onSectionReviewPick(sentenceId) {
    // WHY: 사용자가 문장을 고름 → sentence_index 변경 허용 (design/17)
    var idx = -1;
    for (var i = 0; i < state.sentences.length; i++) {
      if (
        state.sentences[i] &&
        String(state.sentences[i].id) === String(sentenceId)
      ) {
        idx = i;
        break;
      }
    }
    if (idx < 0) return;
    closeSectionReview({ resume: false });
    state.sentenceIndex = idx;
    render();
    snapshotActivePaper();
    openNoteOverlay();
  }

  function stripCloseGestureNewlines() {
    // WHY: Enter×3 닫기는 기록이 아님 — 앞 두 Enter가 남긴 \n\n 을 저장 전에 제거
    if (!el.noteTextarea) return;
    let v = el.noteTextarea.value;
    let removed = 0;
    while (removed < 2 && v.endsWith("\n")) {
      v = v.slice(0, -1);
      removed += 1;
    }
    if (removed) el.noteTextarea.value = v;
  }

  /** @returns {boolean} true if overlay closed */
  function registerNoteEnterClose(ev) {
    const now = Date.now();
    if (now - noteUi.lastEnterAt <= NOTE_ENTER_GAP_MS) {
      noteUi.enterStreak += 1;
    } else {
      noteUi.enterStreak = 1;
    }
    noteUi.lastEnterAt = now;
    if (noteUi.enterStreak < 3) return false;
    if (ev) ev.preventDefault();
    noteUi.enterStreak = 0;
    noteUi.lastEnterAt = 0;
    stripCloseGestureNewlines();
    closeNoteOverlay();
    return true;
  }

  function blurNoteTextarea() {
    // WHY: 입력칸에서 커서만 빼기 (←/→ · Space 용)
    if (!el.noteTextarea) return;
    el.noteTextarea.blur();
    if (el.noteSheet) el.noteSheet.focus();
  }

  /** Esc로 노트 닫을 때 브라우저 전체화면이 같이 풀리면 즉시 복구 */
  let noteEscFsGuard = false;

  function requestBrowserFullscreen() {
    const root = document.documentElement;
    const req =
      root.requestFullscreen ||
      root.webkitRequestFullscreen ||
      root.msRequestFullscreen;
    if (!req) return Promise.resolve();
    return Promise.resolve(req.call(root)).catch(() => {});
  }

  async function lockEscapeWhileNoteInFs() {
    // WHY: Chromium 은 FS 중 Esc 해제를 preventDefault 로 못 막는 경우가 많음
    if (!isBrowserFullscreen()) return;
    try {
      if (navigator.keyboard && typeof navigator.keyboard.lock === "function") {
        await navigator.keyboard.lock(["Escape"]);
      }
    } catch (_) {
      /* ignore — fallback 은 Esc 직후 FS 재진입 */
    }
  }

  function unlockEscapeKeys() {
    try {
      if (navigator.keyboard && typeof navigator.keyboard.unlock === "function") {
        navigator.keyboard.unlock();
      }
    } catch (_) {
      /* ignore */
    }
  }

  function closeNoteOverlayFromEscape(ev) {
    // WHY: 노트 열림 중 Esc = 입력창 닫기 우선 · 브라우저 FS 는 유지
    if (!isNoteOpen()) return;
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function") {
        ev.stopImmediatePropagation();
      }
    }
    const wantFs = isBrowserFullscreen();
    if (wantFs) {
      noteEscFsGuard = true;
      // WHY: 같은 키 제스처로 FS 재요청 — fullscreenchange 만으로는 user gesture 없음
      document.body.classList.add("is-browser-fullscreen");
      requestBrowserFullscreen();
    }
    unlockEscapeKeys();
    closeNoteOverlay();
    if (wantFs) {
      window.setTimeout(() => {
        if (!isBrowserFullscreen()) {
          document.body.classList.add("is-browser-fullscreen");
          requestBrowserFullscreen().finally(() => {
            noteEscFsGuard = false;
          });
        } else {
          noteEscFsGuard = false;
        }
      }, 30);
    }
  }

  function onNoteTextareaKeydown(ev) {
    if (ev.isComposing) return;
    if (ev.key === "Escape") {
      closeNoteOverlayFromEscape(ev);
      return;
    }
    if (ev.key !== "Enter" || ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey) {
      if (ev.key !== "Enter") {
        noteUi.enterStreak = 0;
      }
      return;
    }
    registerNoteEnterClose(ev);
  }

  async function deleteActivePaperCache() {
    const p = papers[activePaperIndex];
    if (!p || isMockPaper(p)) return;
    const label = shortTitle(p.title, 40);
    const ok = window.confirm(
      `「${label}」보관본을 삭제할까요?\n다음에 같은 파일을 열면 다시 분석합니다.`
    );
    if (!ok) return;

    setLoading(true);
    setUploadStatus("보관본 삭제 중…", "busy");
    try {
      let res;
      if (p.cacheId) {
        res = await fetch(`/api/cache/papers/${encodeURIComponent(p.cacheId)}`, {
          method: "DELETE",
        });
      } else {
        res = await fetch("/api/cache/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: p.title,
            source: p.source || "pdf",
          }),
        });
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        if (res.status !== 404) {
          throw new Error(data.message || "삭제에 실패했습니다.");
        }
      }

      const removedIdx = activePaperIndex;
      papers.splice(removedIdx, 1);
      const reals = realPaperIndices();
      if (reals.length) {
        const prefer =
          reals.find((i) => i >= removedIdx) ?? reals[reals.length - 1];
        activePaperIndex = prefer;
        hydrateStateFromPaper(papers[activePaperIndex]);
        uiPhase = "ready";
        render();
        renderPaperTabs();
        el.stageBadge.textContent =
          reals.length > 1
            ? `${reals.indexOf(activePaperIndex) + 1}/${reals.length} · ${shortTitle(state.title, 40)}`
            : state.title || "ready";
        setUploadStatus("보관본 삭제됨 · 파일을 다시 열면 재분석", "");
      } else {
        papers = [];
        activePaperIndex = 0;
        await loadMock();
        setUploadStatus("보관본 삭제됨 · 파일을 다시 열어 주세요", "");
      }
      updateCacheDeleteBtn();
    } catch (err) {
      console.error(err);
      setUploadStatus(String(err.message || err), "error");
    } finally {
      setLoading(false);
    }
  }

  async function loadMock() {
    setLoading(true);
    setUploadStatus("mock 불러오는 중…", "busy");
    try {
      const res = await fetch("/api/session/mock");
      if (!res.ok) throw new Error("mock session failed");
      const data = await res.json();
      applySession(data, "mock", { asNewTab: false });
      setUploadStatus("");
    } catch (err) {
      console.error(err);
      uiPhase = "error";
      el.stageBadge.textContent = "skeleton · mock load failed";
      setSentenceDisplay("mock 세션을\n불러오지 못했어요.", true);
      setUploadStatus("mock 실패", "error");
    } finally {
      setLoading(false);
    }
  }

  async function ingestPdf(file) {
    if (!file) return;
    const name = file.name || "document.pdf";
    if (!/\.(pdf|docx)$/i.test(name)) {
      setUploadStatus("PDF 또는 Word(.docx)만 가능합니다.", "error");
      return;
    }
    if (/\.doc$/i.test(name) && !/\.docx$/i.test(name)) {
      setUploadStatus("옛 .doc 은 Word에서 .docx 로 저장해 주세요.", "error");
      return;
    }

    setLoading(true);
    setUploadStatus(`읽는 중… 0% · ${name}`, "busy");
    el.stageBadge.textContent = `다듬는 중 · ${name}`;
    // WHY: 이미 열린 논문이 있으면 화면은 유지 — 상태만 헤더에 표시
    if (!papers.length) {
      uiPhase = "loading";
      setSentenceDisplay(
        "논문을 읽고 있어요.\n잡음을 걸러 읽기 좋게\n다듬는 중이에요.",
        true
      );
    }

    const body = new FormData();
    body.append("file", file, name);

    try {
      const res = await fetch("/api/ingest", { method: "POST", body });
      const start = await res.json().catch(() => ({}));
      if (!res.ok || start.ok === false) {
        throw new Error(start.message || `업로드 실패 (${res.status})`);
      }
      const jobId = start.job_id;
      if (!jobId) {
        throw new Error("작업 ID를 받지 못했어요.");
      }

      let data = null;
      for (;;) {
        await new Promise((r) => setTimeout(r, 400));
        const stRes = await fetch(`/api/ingest/jobs/${encodeURIComponent(jobId)}`);
        const st = await stRes.json().catch(() => ({}));
        if (!stRes.ok && stRes.status === 404) {
          throw new Error(st.message || "작업을 찾을 수 없어요.");
        }
        const pct = typeof st.percent === "number" ? st.percent : 0;
        setUploadStatus(`읽는 중… ${pct}% · ${name}`, "busy");
        if (st.message) {
          el.stageBadge.textContent = `${st.message} · ${name}`;
        }
        if (st.done) {
          if (st.ok === false && !st.session_id) {
            throw new Error(st.message || "처리에 실패했어요.");
          }
          data = st;
          break;
        }
      }

      applySession(data, "ready", { asNewTab: true });
      const nS = state.sentences.length;
      const nF = state.figures.length;
      if (data.from_cache) {
        setUploadStatus(`보관본 · 문장 ${nS} · 그림 ${nF}`, "");
      } else if (data.debone) {
        const cached = data.cached ? " · 보관됨" : "";
        setUploadStatus(`문장 ${nS} · 그림 ${nF} · cleaned${cached}`, "");
      } else {
        const warn = (data.warnings && data.warnings[0]) || "raw";
        setUploadStatus(`문장 ${nS} · 그림 ${nF} · 정제 실패(${warn}) · raw`, "error");
      }
    } catch (err) {
      console.error(err);
      if (!papers.length) {
        uiPhase = "error";
        el.stageBadge.textContent = "ingest failed";
        setSentenceDisplay(String(err.message || err), true);
      }
      setUploadStatus(String(err.message || err), "error");
    } finally {
      setLoading(false);
      el.pdfInput.value = "";
    }
  }

  async function ingestFiles(fileList) {
    const files = [...(fileList || [])].filter(Boolean);
    if (!files.length) return;
    for (const file of files) {
      await ingestPdf(file);
    }
  }

  /* ---------- Splitter: 드래그 접기 비활성 ---------- */
  // WHY: TTS·크롭 우선 — 스플리터/스트립으로 접기·펴기 하지 않음
  el.figureStrip.hidden = true;
  el.splitter.removeAttribute("tabindex");

  el.figPrev.addEventListener("click", () => advanceFigure(-1));
  el.figNext.addEventListener("click", () => advanceFigure(1));
  el.sentPrev.addEventListener("click", () => advanceSentence(-1));
  el.sentNext.addEventListener("click", () => advanceSentence(1));

  function plainSentenceText(html) {
    const d = document.createElement("div");
    d.innerHTML = html || "";
    return (d.textContent || "").replace(/\s+/g, " ").trim();
  }

  function setTtsSpeakingUi(on) {
    if (el.sentenceFrame) el.sentenceFrame.classList.toggle("is-speaking", !!on);
    if (el.noteSheet) el.noteSheet.classList.toggle("is-speaking", !!on);
  }

  function stopTtsEngineOnly() {
    ttsFetchGen += 1;
    // WHY: Signalsmith / HTMLAudio 공통 중단 (tts_stretch.js)
    if (window.AsrStretch && typeof window.AsrStretch.stop === "function") {
      try {
        window.AsrStretch.stop();
      } catch (_) {
        /* ignore */
      }
    }
    if (ttsAudio) {
      try {
        ttsAudio.pause();
      } catch (_) {
        /* ignore */
      }
      ttsAudio = null;
    }
    if (ttsObjectUrl) {
      try {
        URL.revokeObjectURL(ttsObjectUrl);
      } catch (_) {
        /* ignore */
      }
      ttsObjectUrl = null;
    }
    setTtsSpeakingUi(false);
  }

  function stopTts() {
    stopTtsEngineOnly();
    // WHY: TTS·문장 이동 시 사용자 목소리도 겹치지 않게 끊음
    stopVoicePlayback();
  }

  /**
   * 정속 MP3 버퍼 → 클라이언트 배속 재생 (Signalsmith 우선).
   * @param {ArrayBuffer} buf
   * @param {number} speakingRate
   * @param {{ onEnded?: function, onError?: function }} handlers
   */
  async function playTtsBuffer(buf, speakingRate, handlers) {
    handlers = handlers || {};
    if (window.AsrStretch && typeof window.AsrStretch.play === "function") {
      await window.AsrStretch.play({
        arrayBuffer: buf,
        rate: speakingRate,
        onEnded: handlers.onEnded,
        onError: handlers.onError,
      });
      return;
    }
    // 레거시 폴백 (AsrStretch 미로드)
    const blob = new Blob([buf], { type: "audio/mpeg" });
    ttsObjectUrl = URL.createObjectURL(blob);
    ttsAudio = new Audio(ttsObjectUrl);
    try {
      ttsAudio.preservesPitch = true;
      ttsAudio.playbackRate = speakingRate || 1;
    } catch (_) {
      /* ignore */
    }
    ttsAudio.onended = () => {
      if (handlers.onEnded) handlers.onEnded();
    };
    ttsAudio.onerror = () => {
      if (handlers.onError) handlers.onError(new Error("play failed"));
    };
    await ttsAudio.play();
  }

  function loadTtsSettings() {
    try {
      let raw = localStorage.getItem(TTS_STORAGE_KEY);
      if (!raw) raw = localStorage.getItem("asr.tts.v1");
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data && typeof data.mode === "string" && TTS_MODES.has(data.mode)) {
        ttsSettings.mode = data.mode;
      }
      if (data && typeof data.voice === "string" && data.voice) {
        ttsSettings.voice = data.voice;
      }
      if (data && typeof data.speakingRate === "number") {
        ttsSettings.speakingRate = Math.min(
          2.2,
          Math.max(0.5, data.speakingRate)
        );
      }
    } catch (_) {
      /* ignore */
    }
  }

  function saveTtsSettings() {
    try {
      localStorage.setItem(
        TTS_STORAGE_KEY,
        JSON.stringify({
          mode: ttsSettings.mode,
          voice: ttsSettings.voice,
          speakingRate: ttsSettings.speakingRate,
        })
      );
    } catch (_) {
      /* ignore */
    }
  }

  function listTtsVoiceIds() {
    if (!el.ttsVoice || !el.ttsVoice.options.length) {
      return [ttsSettings.voice || "en-US-Neural2-D"];
    }
    const ids = [];
    for (const opt of el.ttsVoice.options) {
      const v = String(opt.value || "").trim();
      if (v && v !== "undefined" && v !== "null") ids.push(v);
    }
    return ids.length ? ids : [ttsSettings.voice || "en-US-Neural2-D"];
  }

  function listTtsVoiceIdsForLocale(locale) {
    const prefix = String(locale || "en-US") + "-";
    const matched = listTtsVoiceIds().filter((id) => id.startsWith(prefix));
    if (matched.length) return matched;
    if (locale !== "en-US") return listTtsVoiceIdsForLocale("en-US");
    return [ttsSettings.voice || "en-US-Neural2-D"];
  }

  function pickWeightedLocale(mode) {
    const weights = TTS_LOCALE_WEIGHTS[mode];
    if (!weights) return "en-US";
    const entries = Object.entries(weights).filter(([, w]) => w > 0);
    if (!entries.length) return "en-US";
    let r = Math.random();
    let acc = 0;
    for (const [locale, w] of entries) {
      acc += w;
      if (r <= acc) return locale;
    }
    return entries[entries.length - 1][0];
  }

  function randomInRange(min, max) {
    return min + Math.random() * (max - min);
  }

  /**
   * 재생용 목소리·속도.
   * @param {{ fromForm?: boolean }} opts fromForm=true면 다이얼로그 모드 선택 기준
   */
  function pickTtsPlaybackParams(opts) {
    const fromForm = !!(opts && opts.fromForm);
    const mode = fromForm && el.ttsMode ? el.ttsMode.value : ttsSettings.mode;
    if (TTS_RANDOM_MODES.has(mode)) {
      const band = TTS_RATE_BANDS[mode];
      const locale = pickWeightedLocale(mode);
      const voices = listTtsVoiceIdsForLocale(locale);
      const voice = voices[Math.floor(Math.random() * voices.length)];
      const rate = Math.round(randomInRange(band.min, band.max) * 100) / 100;
      return { voice, speakingRate: rate, mode };
    }
    if (fromForm) {
      return {
        voice: resolveTtsVoiceFromForm(),
        speakingRate: el.ttsRate
          ? Number(el.ttsRate.value) || 1
          : ttsSettings.speakingRate,
        mode: "fixed",
      };
    }
    return {
      voice: ttsSettings.voice,
      speakingRate: ttsSettings.speakingRate,
      mode: "fixed",
    };
  }

  function updateTtsModeUi() {
    const mode = (el.ttsMode && el.ttsMode.value) || ttsSettings.mode;
    const random = TTS_RANDOM_MODES.has(mode);
    if (el.ttsVoiceField) el.ttsVoiceField.classList.toggle("is-dimmed", random);
    if (el.ttsRateField) el.ttsRateField.classList.toggle("is-dimmed", random);
    if (el.ttsModeHint) {
      if (TTS_RANDOM_MODES.has(mode)) {
        el.ttsModeHint.textContent =
          "재생마다 목소리와 속도가 바뀝니다.";
      } else {
        el.ttsModeHint.textContent =
          "아래에서 고른 목소리와 속도로 고정 재생합니다.";
      }
    }
  }

  async function ensureTtsVoicesLoaded() {
    if (!el.ttsVoice) return;
    // 잘못된 value="undefined" 옵션이 남아 있으면 다시 채움
    const bad =
      el.ttsVoice.options.length > 0 &&
      [...el.ttsVoice.options].some(
        (o) => !o.value || o.value === "undefined" || o.value === "null"
      );
    if (el.ttsVoice.options.length > 0 && !bad) return;
    try {
      const res = await fetch("/api/tts/voices");
      const data = await res.json();
      const voices = (data && data.voices) || [];
      el.ttsVoice.innerHTML = "";
      for (const v of voices) {
        // API: { id, label } — name 아님
        const id = (v && (v.id || v.name)) || "";
        if (!id || id === "undefined") continue;
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = (v && v.label) || id;
        el.ttsVoice.appendChild(opt);
      }
      if (!el.ttsVoice.options.length) {
        const opt = document.createElement("option");
        opt.value = ttsSettings.voice || "en-US-Neural2-D";
        opt.textContent = opt.value;
        el.ttsVoice.appendChild(opt);
      }
      if (data && data.default_voice && typeof data.default_voice === "string") {
        if (!ttsSettings.voice || ttsSettings.voice === "undefined") {
          ttsSettings.voice = data.default_voice;
        }
      }
    } catch (_) {
      el.ttsVoice.innerHTML = "";
      const opt = document.createElement("option");
      opt.value = ttsSettings.voice || "en-US-Neural2-D";
      opt.textContent = opt.value;
      el.ttsVoice.appendChild(opt);
    }
  }

  function resolveTtsVoiceFromForm() {
    let voice = (el.ttsVoice && el.ttsVoice.value) || ttsSettings.voice || "";
    voice = String(voice).trim();
    if (!voice || voice === "undefined" || voice === "null") {
      voice = "en-US-Neural2-D";
    }
    return voice;
  }

  function syncTtsForm() {
    if (el.ttsMode) el.ttsMode.value = ttsSettings.mode || "fixed";
    if (el.ttsVoice) el.ttsVoice.value = ttsSettings.voice;
    if (el.ttsRate) el.ttsRate.value = String(ttsSettings.speakingRate);
    if (el.ttsRateOut) {
      el.ttsRateOut.textContent = Number(ttsSettings.speakingRate).toFixed(2);
    }
    updateTtsModeUi();
  }

  async function openTtsSettings() {
    await ensureTtsVoicesLoaded();
    syncTtsForm();
    if (el.ttsDialog && typeof el.ttsDialog.showModal === "function") {
      el.ttsDialog.showModal();
    }
  }

  async function speakCurrentSentence() {
    const nS = state.sentences.length;
    if (!nS) return;
    const sent = state.sentences[state.sentenceIndex];
    // WHY: rich HTML 을 서버로 보냄 — 첨자·Title: 은 TTS spoken 정규화 (tts_speak)
    const text = String((sent && sent.text) || "").trim();
    if (!plainSentenceText(text)) {
      setUploadStatus("읽을 문장이 없습니다.", "error");
      return;
    }

    // WHY: 다시 클릭 = 처음부터 다시 — 먼저 끊고 재요청
    stopTts();
    const gen = ttsFetchGen;
    if (ttsSettings.mode !== "fixed") {
      await ensureTtsVoicesLoaded();
    }
    const params = pickTtsPlaybackParams({ fromForm: false });
    setTtsSpeakingUi(true);
    // WHY: 랜덤 모드에서 배속·목소리를 보여 주면 예측이 생겨 난이도가 깎임
    setUploadStatus("듣는 중…", "busy");

    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          voice: params.voice,
          speaking_rate: params.speakingRate,
        }),
      });
      if (gen !== ttsFetchGen) return;
      if (!res.ok) {
        let msg = "TTS 실패";
        try {
          const err = await res.json();
          msg = (err && err.message) || msg;
        } catch (_) {
          /* ignore */
        }
        setTtsSpeakingUi(false);
        setUploadStatus(msg, "error");
        return;
      }
      const buf = await res.arrayBuffer();
      if (gen !== ttsFetchGen) return;
      // WHY: 서버는 정속 캐시 — 배속은 AsrStretch (Signalsmith → preservesPitch)
      await playTtsBuffer(buf, params.speakingRate, {
        onEnded: () => {
          if (gen !== ttsFetchGen) return;
          setTtsSpeakingUi(false);
          setUploadStatus("");
        },
        onError: () => {
          if (gen !== ttsFetchGen) return;
          setTtsSpeakingUi(false);
          setUploadStatus("재생 실패", "error");
        },
      });
      if (gen !== ttsFetchGen) return;
      setUploadStatus("");
    } catch (err) {
      if (gen !== ttsFetchGen) return;
      setTtsSpeakingUi(false);
      setUploadStatus("TTS 오류: " + (err && err.message ? err.message : err), "error");
    }
  }

  // WHY: 문장 클릭 = TTS (확대/접기 아님)
  el.sentenceFrame.addEventListener("click", (ev) => {
    const sel = window.getSelection && window.getSelection();
    if (sel && String(sel).length > 0) return;
    ev.preventDefault();
    speakCurrentSentence();
  });

  /* ---------- 그림 전체화면: 드래그 크롭 확대 ---------- */
  let cropDrag = null;
  let suppressFigureClick = false;

  function localPoint(ev) {
    const rect = el.figureViewport.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  }

  el.figureViewport.addEventListener("pointerdown", (ev) => {
    if (!layout.fullscreen) return;
    if (ev.button != null && ev.button !== 0) return;
    // 확대 중이면 드래그 대신 클릭으로만 축소
    if (cropZoom.active) return;
    ev.preventDefault();
    const p = localPoint(ev);
    cropDrag = {
      pointerId: ev.pointerId,
      x0: p.x,
      y0: p.y,
      x1: p.x,
      y1: p.y,
      moved: false,
    };
    try {
      el.figureViewport.setPointerCapture(ev.pointerId);
    } catch (_) {
      /* ignore */
    }
  });

  el.figureViewport.addEventListener("pointermove", (ev) => {
    if (!cropDrag || ev.pointerId !== cropDrag.pointerId) return;
    const p = localPoint(ev);
    cropDrag.x1 = p.x;
    cropDrag.y1 = p.y;
    if (Math.hypot(p.x - cropDrag.x0, p.y - cropDrag.y0) > 6) {
      cropDrag.moved = true;
      setRubberband(cropDrag.x0, cropDrag.y0, cropDrag.x1, cropDrag.y1);
    }
  });

  function endCropDrag(ev) {
    if (!cropDrag || (ev && ev.pointerId !== cropDrag.pointerId)) return;
    const drag = cropDrag;
    cropDrag = null;
    hideRubberband();
    if (drag.moved) {
      suppressFigureClick = true;
      setCropFromViewportRect(drag.x0, drag.y0, drag.x1, drag.y1);
      window.setTimeout(() => {
        suppressFigureClick = false;
      }, 0);
    }
  }

  el.figureViewport.addEventListener("pointerup", endCropDrag);
  el.figureViewport.addEventListener("pointercancel", endCropDrag);

  el.figureFrame.addEventListener("click", (ev) => {
    if (suppressFigureClick) {
      ev.preventDefault();
      ev.stopPropagation();
      return;
    }
    // 전체화면 + 크롭 확대 중 → 클릭하면 축소만 (캡션·FS 유지)
    if (layout.fullscreen && cropZoom.active) {
      ev.preventDefault();
      clearCropZoom();
      return;
    }
    ev.preventDefault();
    focusFigure();
  });
  el.figureFrame.setAttribute("tabindex", "0");
  el.figureFrame.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      if (layout.fullscreen && cropZoom.active) {
        clearCropZoom();
        return;
      }
      focusFigure();
    }
  });
  // WHY: Enter 는 성찰 노트 (docs/design/16). TTS 는 문장 클릭만.

  if (el.ttsSettingsBtn) {
    el.ttsSettingsBtn.addEventListener("click", () => openTtsSettings());
  }
  if (el.ttsRate) {
    el.ttsRate.addEventListener("input", () => {
      if (el.ttsRateOut) {
        el.ttsRateOut.textContent = Number(el.ttsRate.value).toFixed(2);
      }
    });
  }
  if (el.ttsMode) {
    el.ttsMode.addEventListener("change", () => updateTtsModeUi());
  }
  if (el.ttsForm) {
    el.ttsForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (el.ttsMode) {
        const m = el.ttsMode.value;
        if (TTS_MODES.has(m)) ttsSettings.mode = m;
      }
      if (el.ttsVoice && el.ttsVoice.value) {
        const v = resolveTtsVoiceFromForm();
        ttsSettings.voice = v;
        el.ttsVoice.value = v;
      }
      if (el.ttsRate) {
        ttsSettings.speakingRate = Number(el.ttsRate.value) || 1;
      }
      saveTtsSettings();
      if (el.ttsDialog) el.ttsDialog.close();
      setUploadStatus("TTS 설정 저장됨");
      window.setTimeout(() => setUploadStatus(""), 1500);
    });
  }
  if (el.ttsDialogClose) {
    el.ttsDialogClose.addEventListener("click", () => {
      stopTts();
      if (el.ttsDialog) el.ttsDialog.close();
    });
  }

  function setTtsSampleStatus(text, kind) {
    if (!el.ttsSampleStatus) return;
    el.ttsSampleStatus.textContent = text || "";
    el.ttsSampleStatus.classList.toggle("is-error", kind === "error");
  }

  /** 설정 폼 기준으로 예시 재생 (랜덤 모드면 그때그때 뽑음) */
  async function playTtsPreview() {
    const text = (
      (el.ttsSampleText && el.ttsSampleText.textContent) ||
      "The Ni catalyst remains stable after pretreatment."
    )
      .replace(/\s+/g, " ")
      .trim();
    await ensureTtsVoicesLoaded();
    const params = pickTtsPlaybackParams({ fromForm: true });

    stopTts();
    const gen = ttsFetchGen;
    setTtsSampleStatus("준비 중…");
    if (el.ttsPreviewBtn) el.ttsPreviewBtn.disabled = true;
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          voice: params.voice,
          speaking_rate: params.speakingRate,
        }),
      });
      if (gen !== ttsFetchGen) return;
      if (!res.ok) {
        let msg = "미리듣기 실패";
        try {
          const err = await res.json();
          msg = (err && err.message) || msg;
        } catch (_) {
          /* ignore */
        }
        setTtsSampleStatus(msg, "error");
        return;
      }
      const buf = await res.arrayBuffer();
      if (gen !== ttsFetchGen) return;
      await playTtsBuffer(buf, params.speakingRate, {
        onEnded: () => {
          if (gen !== ttsFetchGen) return;
          setTtsSampleStatus("");
        },
        onError: () => {
          if (gen !== ttsFetchGen) return;
          setTtsSampleStatus("재생 실패", "error");
        },
      });
      if (gen !== ttsFetchGen) return;
      setTtsSampleStatus("재생 중");
    } catch (err) {
      if (gen !== ttsFetchGen) return;
      setTtsSampleStatus(
        "오류: " + (err && err.message ? err.message : String(err)),
        "error"
      );
    } finally {
      if (el.ttsPreviewBtn) el.ttsPreviewBtn.disabled = false;
    }
  }

  if (el.ttsPreviewBtn) {
    el.ttsPreviewBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      playTtsPreview();
    });
  }

  /* ---------- 가림창: 사용자가 옆 모니터로 옮긴 뒤 F11 ---------- */
  let veilWin = null;

  function veilBg() {
    return (
      getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() ||
      "#0f0f0f"
    );
  }

  function closeVeilWindow() {
    if (veilWin && !veilWin.closed) {
      try {
        veilWin.close();
      } catch (_) {
        /* ignore */
      }
    }
    veilWin = null;
  }

  function openVeilWindow() {
    // 자동 배치/FS 없음 — 창만 띄우고 사용자가 옆 모니터 + F11
    if (veilWin && !veilWin.closed) {
      try {
        veilWin.focus();
      } catch (_) {
        /* ignore */
      }
      return;
    }
    const bg = veilBg();
    const url =
      "/static/veil.html?bg=" +
      encodeURIComponent(bg.startsWith("#") ? bg : "#0f0f0f");
    const w = window.open(
      url,
      "asr_dual_veil",
      "popup=yes,width=900,height=700,left=80,top=80"
    );
    if (!w) {
      setUploadStatus("가림창: 팝업을 허용해 주세요.", "error");
      return;
    }
    veilWin = w;
    w.addEventListener("beforeunload", () => {
      if (veilWin === w) veilWin = null;
    });
  }

  function toggleVeilWindow() {
    if (veilWin && !veilWin.closed) {
      closeVeilWindow();
      return;
    }
    openVeilWindow();
  }

  // 더블클릭 = 가림창 (브라우저 전체화면 F · 노트 열린 때는 비활성)
  document.addEventListener("dblclick", (ev) => {
    if (isBrowserFullscreen()) return;
    if (isNoteOpen()) return;
    if (ev.target && ev.target.closest) {
      if (ev.target.closest("#noteOverlay")) return;
      if (ev.target.closest("#splitter")) return;
      if (ev.target.closest(".upload-bar")) return;
      if (ev.target.closest(".app-header")) return;
      if (ev.target.closest(".paper-tabs")) return;
    }
    ev.preventDefault();
    openVeilWindow();
  });

  function isBrowserFullscreen() {
    return !!(
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.msFullscreenElement
    );
  }

  /* ---------- 뽀모도로: 25분 읽기 / 5분 휴식 (UI는 알림·휴식만) ---------- */
  const POMO_WORK_MS = 25 * 60 * 1000;
  const POMO_BREAK_MS = 5 * 60 * 1000;
  const POMO_ALERT_MS = 30 * 1000;
  /** @type {"idle"|"work"|"alert"|"breakPending"|"break"|"breakDone"} */
  let pomoPhase = "idle";
  let pomoDeadline = 0;
  let pomoTickId = 0;
  let pomoAudioCtx = null;

  function formatPomoMmSs(ms) {
    const s = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + ":" + String(r).padStart(2, "0");
  }

  function ensurePomoAudio() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!pomoAudioCtx) pomoAudioCtx = new AC();
    if (pomoAudioCtx.state === "suspended") {
      pomoAudioCtx.resume().catch(() => {});
    }
    return pomoAudioCtx;
  }

  function playPomoTone(freqs, durSec) {
    try {
      const ctx = ensurePomoAudio();
      if (!ctx) return;
      const t0 = ctx.currentTime;
      freqs.forEach((freq, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.08, t0 + 0.02 + i * 0.05);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + durSec + i * 0.08);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t0 + i * 0.08);
        osc.stop(t0 + durSec + i * 0.12 + 0.05);
      });
    } catch (_) {
      /* ignore */
    }
  }

  function playPomoAlertSound() {
    playPomoTone([523.25, 659.25, 783.99], 0.35);
  }

  function playPomoBreakDoneSound() {
    playPomoTone([392, 523.25], 0.45);
  }

  function clearPomoTick() {
    if (pomoTickId) {
      window.clearInterval(pomoTickId);
      pomoTickId = 0;
    }
  }

  function hidePomoAlert() {
    if (el.pomoAlert) el.pomoAlert.hidden = true;
  }

  function hidePomoBreak() {
    if (el.pomoBreak) el.pomoBreak.hidden = true;
  }

  function showPomoAlert() {
    if (!el.pomoAlert) return;
    el.pomoAlert.hidden = false;
    updatePomoAlertUi();
  }

  function showPomoBreakPanel(kind) {
    if (!el.pomoBreak) return;
    el.pomoBreak.hidden = false;
    if (kind === "done") {
      if (el.pomoBreakLabel) el.pomoBreakLabel.textContent = "휴식 끝";
      if (el.pomoBreakTime) el.pomoBreakTime.textContent = "0:00";
      if (el.pomoBreakHint) el.pomoBreakHint.textContent = "F — 읽기 시작";
    } else {
      if (el.pomoBreakLabel) el.pomoBreakLabel.textContent = "휴식";
      if (el.pomoBreakHint) el.pomoBreakHint.textContent = "F — 바로 읽기 재개";
      updatePomoBreakUi();
    }
  }

  function updatePomoAlertUi() {
    if (!el.pomoAlertTime) return;
    el.pomoAlertTime.textContent = formatPomoMmSs(pomoDeadline - Date.now());
  }

  function updatePomoBreakUi() {
    if (!el.pomoBreakTime) return;
    el.pomoBreakTime.textContent = formatPomoMmSs(pomoDeadline - Date.now());
  }

  function stopPomoWorkOnly() {
    clearPomoTick();
    hidePomoAlert();
    if (pomoPhase === "work" || pomoPhase === "alert" || pomoPhase === "breakPending") {
      pomoPhase = "idle";
      pomoDeadline = 0;
    }
  }

  function startPomoWork() {
    clearPomoTick();
    hidePomoAlert();
    hidePomoBreak();
    ensurePomoAudio();
    pomoPhase = "work";
    pomoDeadline = Date.now() + POMO_WORK_MS;
    pomoTickId = window.setInterval(onPomoTick, 250);
  }

  function startPomoAlert() {
    clearPomoTick();
    hidePomoBreak();
    pomoPhase = "alert";
    pomoDeadline = Date.now() + POMO_ALERT_MS;
    showPomoAlert();
    playPomoAlertSound();
    pomoTickId = window.setInterval(onPomoTick, 250);
  }

  function startPomoBreak() {
    clearPomoTick();
    hidePomoAlert();
    pomoPhase = "break";
    pomoDeadline = Date.now() + POMO_BREAK_MS;
    showPomoBreakPanel("active");
    pomoTickId = window.setInterval(onPomoTick, 250);
  }

  function finishPomoBreak() {
    clearPomoTick();
    pomoPhase = "breakDone";
    pomoDeadline = 0;
    showPomoBreakPanel("done");
    playPomoBreakDoneSound();
  }

  function onPomoTick() {
    const left = pomoDeadline - Date.now();
    if (pomoPhase === "work") {
      if (left <= 0) startPomoAlert();
      return;
    }
    if (pomoPhase === "alert") {
      updatePomoAlertUi();
      if (left <= 0) {
        hidePomoAlert();
        // 알림만 종료 — 아직 FS 면 휴식 대기, 이미 창모드면 휴식 시작
        if (isBrowserFullscreen()) {
          pomoPhase = "breakPending";
          clearPomoTick();
        } else {
          startPomoBreak();
        }
      }
      return;
    }
    if (pomoPhase === "break") {
      updatePomoBreakUi();
      if (left <= 0) finishPomoBreak();
    }
  }

  function onPomoEnterFullscreen() {
    // 휴식 중 F → 휴식 취소 후 읽기 / 휴식 끝·idle → 읽기 시작
    if (pomoPhase === "break" || pomoPhase === "breakDone" || pomoPhase === "idle") {
      startPomoWork();
      return;
    }
    // alert / breakPending / work 중 재진입은 유지
  }

  function onPomoExitFullscreen() {
    if (pomoPhase === "work") {
      // 읽기 미완료 해제 → 휴식 없음
      stopPomoWorkOnly();
      return;
    }
    if (pomoPhase === "alert" || pomoPhase === "breakPending") {
      startPomoBreak();
    }
  }

  async function toggleBrowserFullscreen() {
    // F = 본창만. 가림창은 건드리지 않음.
    try {
      ensurePomoAudio();
      if (isBrowserFullscreen()) {
        const exit =
          document.exitFullscreen ||
          document.webkitExitFullscreen ||
          document.msExitFullscreen;
        if (exit) await exit.call(document);
      } else {
        const elRoot = document.documentElement;
        const req =
          elRoot.requestFullscreen ||
          elRoot.webkitRequestFullscreen ||
          elRoot.msRequestFullscreen;
        if (req) await req.call(elRoot);
      }
    } catch (err) {
      console.warn("fullscreen failed", err);
    }
  }

  function isFocusInNoteTextarea() {
    return !!(el.noteTextarea && document.activeElement === el.noteTextarea);
  }

  // WHY: window capture 가 가장 먼저 — FS Esc 와 경쟁
  window.addEventListener(
    "keydown",
    (ev) => {
      if (ev.key !== "Escape") return;
      if (isNoteOpen()) {
        closeNoteOverlayFromEscape(ev);
        return;
      }
      if (isSectionReviewOpen()) {
        ev.preventDefault();
        ev.stopPropagation();
        closeSectionReview();
      }
    },
    true
  );

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && isNoteOpen()) {
      closeNoteOverlayFromEscape(ev);
      return;
    }
    if (ev.key === "Escape" && isSectionReviewOpen()) {
      ev.preventDefault();
      closeSectionReview();
      return;
    }

    // WHY: Enter×3 닫기는 입력칸 포커스 없어도 동작
    if (
      isNoteOpen() &&
      ev.key === "Enter" &&
      !ev.isComposing &&
      !ev.shiftKey &&
      !ev.ctrlKey &&
      !ev.metaKey &&
      !ev.altKey
    ) {
      if (isFocusInNoteTextarea()) {
        // textarea 리스너가 줄바꿈 + streak 처리
        return;
      }
      ev.preventDefault();
      registerNoteEnterClose(ev);
      return;
    }

    // WHY: 노트 열린 채 · 입력칸 커서 없음 → ←/→ 문장 · Space TTS
    if (
      isNoteOpen() &&
      !isFocusInNoteTextarea() &&
      !ev.ctrlKey &&
      !ev.metaKey &&
      !ev.altKey
    ) {
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
        ev.preventDefault();
        const delta = ev.key === "ArrowRight" ? 1 : -1;
        if (ev.shiftKey) {
          advanceFigure(delta);
        } else {
          advanceSentence(delta);
        }
        return;
      }
      if (ev.key === " " || ev.code === "Space") {
        ev.preventDefault();
        playNoteSentence();
        return;
      }
    }

    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    // Alt+←/→ = 활성 논문 탭을 한 칸 이동 (드래그 대안)
    if (
      ev.altKey &&
      !ev.ctrlKey &&
      !ev.metaKey &&
      (ev.key === "ArrowLeft" || ev.key === "ArrowRight")
    ) {
      const real = realPaperIndices();
      if (real.length < 2) return;
      const fromSlot = real.indexOf(activePaperIndex);
      if (fromSlot < 0) return;
      const toSlot = fromSlot + (ev.key === "ArrowRight" ? 1 : -1);
      if (toSlot < 0 || toSlot >= real.length) return;
      ev.preventDefault();
      if (reorderPaper(real[fromSlot], real[toSlot])) {
        renderPaperTabs();
        updatePaperTabChrome();
      }
      return;
    }

    // Enter → 성찰 노트 (TTS dialog / 노트 이미 열림이면 무시)
    if (
      ev.key === "Enter" &&
      !ev.isComposing &&
      !ev.shiftKey &&
      !ev.ctrlKey &&
      !ev.metaKey &&
      !ev.altKey
    ) {
      if (el.ttsDialog && el.ttsDialog.open) return;
      if (isNoteOpen()) return;
      ev.preventDefault();
      openNoteOverlay();
      return;
    }

    // Tab / Shift+Tab = 논문 탭 전환 (mock 제외)
    if (ev.key === "Tab") {
      if (realPaperIndices().length >= 2) {
        ev.preventDefault();
        advancePaper(ev.shiftKey ? -1 : 1);
      }
      return;
    }

    // 1–9 = 해당 논문 탭 (IME 조합 중이면 무시, 코드키로 인식)
    if (!ev.isComposing && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
      let digit = 0;
      if (ev.code && /^Digit[1-9]$/.test(ev.code)) {
        digit = Number(ev.code.slice(5));
      } else if (ev.code && /^Numpad[1-9]$/.test(ev.code)) {
        digit = Number(ev.code.slice(6));
      } else if (ev.key >= "1" && ev.key <= "9") {
        digit = Number(ev.key);
      }
      if (digit >= 1 && digit <= 9) {
        const real = realPaperIndices();
        const idx = digit - 1;
        if (idx < real.length) {
          ev.preventDefault();
          activatePaper(real[idx]);
        }
        return;
      }
    }

    // f = 브라우저 전체화면 (주소창·탭 UI 숨김)
    if (ev.key === "f" || ev.key === "F") {
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
      ev.preventDefault();
      toggleBrowserFullscreen();
      return;
    }

    if (ev.key === "Escape" && layout.fullscreen) {
      ev.preventDefault();
      if (cropZoom.active) {
        clearCropZoom();
        return;
      }
      exitFigureFullscreen();
      return;
    }

    // WHY: ↑ 문장 확대(접기 토글) · ↓ 그림 전체화면(크롭) — 클릭 확대는 없음
    if (ev.key === "ArrowUp") {
      ev.preventDefault();
      focusSentence();
      return;
    }
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      focusFigure();
      return;
    }

    if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
    const delta = ev.key === "ArrowRight" ? 1 : -1;
    // WHY: 그림 전체화면에서는 문장이 없으니 ←/→ 만으로 그림 이동
    if (layout.fullscreen || ev.shiftKey) {
      ev.preventDefault();
      advanceFigure(delta);
    } else {
      ev.preventDefault();
      advanceSentence(delta);
    }
  });

  document.addEventListener("fullscreenchange", onBrowserFullscreenChange);
  document.addEventListener("webkitfullscreenchange", onBrowserFullscreenChange);

  function onBrowserFullscreenChange() {
    const fs = isBrowserFullscreen();
    if (!fs && noteEscFsGuard) {
      // WHY: Esc 가 FS 를 푼 직후 — 레이아웃/뽀모 종료 副作用 없이 즉시 재진입
      document.body.classList.add("is-browser-fullscreen");
      requestBrowserFullscreen().finally(() => {
        if (isBrowserFullscreen()) noteEscFsGuard = false;
        else {
          noteEscFsGuard = false;
          document.body.classList.remove("is-browser-fullscreen");
        }
      });
      return;
    }
    document.body.classList.toggle("is-browser-fullscreen", fs);
    if (fs) {
      onPomoEnterFullscreen();
      if (isNoteOpen()) lockEscapeWhileNoteInFs();
      if (layout.mode === "expanded") applyLayout();
      return;
    }
    unlockEscapeKeys();
    onPomoExitFullscreen();
    // 브라우저 FS 종료 → 기본 읽기 비율(문장 무스크롤)로 (가림창은 유지)
    if (layout.fullscreen) {
      exitFigureFullscreen();
      return;
    }
    if (layout.mode === "expanded") {
      layout.contentSplit = true;
      applyLayout();
      persistLayout();
    }
  }

  window.addEventListener("resize", () => {
    if (layout.mode === "expanded") applyLayout();
    if (layout.fullscreen && cropZoom.active) applyCropZoom();
  });

  restoreLayout();
  // WHY: 접기 UI 제거 — 항상 기본 분할로 시작
  layout.mode = "expanded";
  layout.contentSplit = true;
  layout.fullscreen = false;
  applyLayout();
  loadTtsSettings();

  el.uploadBtn.addEventListener("click", () => el.pdfInput.click());
  if (el.veilBtn) {
    el.veilBtn.addEventListener("click", () => toggleVeilWindow());
  }
  if (el.cacheDeleteBtn) {
    el.cacheDeleteBtn.addEventListener("click", () => deleteActivePaperCache());
  }
  if (el.noteTextarea) {
    el.noteTextarea.addEventListener("keydown", onNoteTextareaKeydown);
    el.noteTextarea.addEventListener("input", () => scheduleNoteSave());
  }
  if (el.noteVoiceBtn) {
    el.noteVoiceBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      toggleNoteVoiceRecord();
    });
  }
  if (el.noteVoicePlayBtn) {
    el.noteVoicePlayBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      playLatestNoteVoice();
    });
  }
  if (el.noteSheet) {
    el.noteSheet.addEventListener("click", (ev) => {
      // WHY: 입력칸(라벨 포함) 클릭 = 커서만 · 그 외 시트 클릭 = TTS
      if (ev.target.closest && ev.target.closest(".note-label, #noteTextarea, .note-voice-row, .note-history")) {
        return;
      }
      ev.preventDefault();
      playNoteSentence();
    });
  }
  if (el.noteOverlay) {
    el.noteOverlay.addEventListener("click", (ev) => {
      // WHY: 프레임(시트) 밖 배경 클릭 = 저장 후 닫기
      if (ev.target === el.noteOverlay) {
        ev.preventDefault();
        closeNoteOverlay();
      }
    });
  }
  if (el.sectionReviewContinue) {
    el.sectionReviewContinue.addEventListener("click", () => {
      closeSectionReview();
    });
  }
  if (el.sectionReviewOverlay) {
    el.sectionReviewOverlay.addEventListener("click", (ev) => {
      if (ev.target === el.sectionReviewOverlay) {
        ev.preventDefault();
        closeSectionReview();
      }
    });
  }
  el.pdfInput.addEventListener("change", () => {
    const list = el.pdfInput.files;
    if (list && list.length) ingestFiles(list);
  });

  // 헤더로 PDF 드래그앤드롭 (여러 개)
  document.body.addEventListener("dragover", (ev) => {
    if (![...ev.dataTransfer.items].some((i) => i.kind === "file")) return;
    ev.preventDefault();
  });
  document.body.addEventListener("drop", (ev) => {
    ev.preventDefault();
    const list = ev.dataTransfer.files;
    if (list && list.length) ingestFiles(list);
  });

  loadMock();
})();
