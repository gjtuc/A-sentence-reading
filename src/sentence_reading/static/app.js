/**
 * 프론트 네비 + 그림 접기 스플리터.
 * INVARIANT: figureIndex 와 sentenceIndex 는 서로 갱신하지 않는다.
 * INVARIANT: 접기/펼치기는 레이아웃만 바꾸고 인덱스는 건드리지 않는다.
 * WHY: 문장을 화면 위로 올려 읽기 — docs/design/11-figure-collapse.md
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
    uploadStatus: document.getElementById("uploadStatus"),
    paperTabs: document.getElementById("paperTabs"),
  };

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
        layout.fullscreen ? "클릭하거나 Esc — 전체화면 종료" : "클릭하면 그림 영역 확대 · 한 번 더 누르면 전체화면"
      );
      el.splitter.setAttribute("aria-valuemin", "0");
      el.splitter.setAttribute("aria-valuemax", "100");
      return;
    }

    el.figureFrame.setAttribute("title", "클릭하면 그림 영역 확대 · 한 번 더 누르면 전체화면");

    if (layout.mode === "collapsed") {
      el.figurePanel.classList.add("is-collapsed");
      el.figureStrip.hidden = false;
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

  /** 문장 박스 클릭: 접힘 ↔ 기본(문장 최소) 토글 */
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
   * 그림 박스 클릭 / ↓:
   * - 글 확대(그림 접힘) → 초기 분할 화면
   * - 기본 → 그림 전체화면(아래에서 상승)
   * - 그림 전체화면 → 초기 분할
   * - 브라우저 FS → 그림 몰입
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
    // WHY: 전체화면 아닐 때 글 박스 확대 상태에서는 그림 FS가 아니라 초기 화면으로
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
    state.sentenceIndex = clamp(state.sentenceIndex + delta, state.sentences.length);
    render();
    snapshotActivePaper();
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

  function shortTitle(title, maxLen) {
    const t = String(title || "").trim() || "Untitled";
    const n = maxLen || 28;
    return t.length > n ? `${t.slice(0, n - 1)}…` : t;
  }

  function isMockPaper(p) {
    if (!p) return true;
    if (p.isMock) return true;
    const t = String(p.title || "");
    return /^Mock paper/i.test(t) || p.sessionId === "ses_mock";
  }

  function renderPaperTabs() {
    const bar = el.paperTabs;
    if (!bar) return;
    bar.innerHTML = "";
    const real = papers
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => !isMockPaper(p));
    if (real.length <= 1) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    real.forEach(({ p, i }, slot) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "paper-tab" + (i === activePaperIndex ? " is-active" : "");
      btn.title = `${slot + 1}. ${p.title || "Untitled"} (키 ${slot + 1})`;
      btn.innerHTML = `<span class="paper-tab-num">${slot + 1}</span>${shortTitle(p.title)}`;
      btn.addEventListener("click", () => activatePaper(i));
      bar.appendChild(btn);
    });
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
      snapshotActivePaper();
      activePaperIndex = i;
      hydrateStateFromPaper(papers[i]);
      uiPhase = "ready";
      render();
      if (layout.fullscreen) applyCropZoom();
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
    el.sentenceText.textContent = text || "";
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

  /* ---------- Splitter drag ---------- */
  let drag = null;

  function onPointerDown(ev, fromCollapsedStrip) {
    if (ev.button != null && ev.button !== 0) return;
    ev.preventDefault();
    layout.contentSplit = false;
    const startY = ev.clientY;
    const startH =
      layout.mode === "collapsed" ? COLLAPSED_PX : el.figurePanel.getBoundingClientRect().height;

    drag = {
      pointerId: ev.pointerId,
      startY,
      startH,
      fromCollapsedStrip: !!fromCollapsedStrip,
      moved: false,
    };

    el.layout.classList.add("is-dragging");
    const target = ev.currentTarget;
    if (target.setPointerCapture) {
      try {
        target.setPointerCapture(ev.pointerId);
      } catch (_) {
        /* ignore */
      }
    }
  }

  function onPointerMove(ev) {
    if (!drag || ev.pointerId !== drag.pointerId) return;
    const dy = ev.clientY - drag.startY;
    if (Math.abs(dy) > 3) drag.moved = true;

    // 그림이 아래: 스플리터를 아래로(dy>0) 끌면 그림 높이 감소
    let next = drag.startH - dy;
    const maxH = maxFigureHeight();

    if (next <= SNAP_COLLAPSE_PX) {
      layout.mode = "collapsed";
      applyLayout();
      return;
    }

    layout.mode = "expanded";
    layout.heightPx = Math.min(Math.max(next, MIN_EXPANDED_PX), maxH);
    applyLayout();
  }

  function onPointerUp(ev) {
    if (!drag || ev.pointerId !== drag.pointerId) return;
    el.layout.classList.remove("is-dragging");

    // 접힌 스트립에서 거의 안 움직이면 클릭으로 펼침
    if (drag.fromCollapsedStrip && !drag.moved) {
      expand();
    } else if (layout.mode === "expanded" && layout.heightPx < SNAP_COLLAPSE_PX) {
      collapse();
    } else {
      persistLayout();
    }
    drag = null;
  }

  function bindDrag(node, fromCollapsedStrip) {
    node.addEventListener("pointerdown", (ev) => onPointerDown(ev, fromCollapsedStrip));
    node.addEventListener("pointermove", onPointerMove);
    node.addEventListener("pointerup", onPointerUp);
    node.addEventListener("pointercancel", onPointerUp);
  }

  bindDrag(el.splitter, false);
  bindDrag(el.figureStrip, true);

  el.splitter.addEventListener("dblclick", (ev) => {
    ev.preventDefault();
    if (layout.mode === "collapsed") expand();
    else collapse();
  });

  el.splitter.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      if (layout.mode === "collapsed") expand();
      else collapse();
      return;
    }
    // ↑/↓ = 문장/그림 프레임 클릭과 동일 (전역 핸들러와 맞춤)
    if (ev.key === "ArrowUp") {
      ev.preventDefault();
      focusSentence();
      return;
    }
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      focusFigure();
    }
  });

  el.figPrev.addEventListener("click", () => advanceFigure(-1));
  el.figNext.addEventListener("click", () => advanceFigure(1));
  el.sentPrev.addEventListener("click", () => advanceSentence(-1));
  el.sentNext.addEventListener("click", () => advanceSentence(1));

  // WHY: 프레임 클릭으로 해당 패널을 크게 — 인덱스는 그대로 (docs/design/11)
  el.sentenceFrame.addEventListener("click", (ev) => {
    // 텍스트 드래그 선택 중이면 무시
    const sel = window.getSelection && window.getSelection();
    if (sel && String(sel).length > 0) return;
    ev.preventDefault();
    focusSentence();
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
  el.sentenceFrame.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      focusSentence();
    }
  });

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

  // 더블클릭 = 가림창 버튼과 동일 (스플리터·헤더 버튼 제외)
  document.addEventListener("dblclick", (ev) => {
    if (ev.target && ev.target.closest) {
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

  async function toggleBrowserFullscreen() {
    // F = 본창만. 가림창은 건드리지 않음.
    try {
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

  document.addEventListener("keydown", (ev) => {
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

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

    // WHY: 브라우저 FS에서는 ↑글 몰입 / ↓그림 몰입 (중간 단계 없음)
    if (ev.key === "ArrowUp") {
      ev.preventDefault();
      if (isBrowserFullscreen()) showImmersiveText();
      else focusSentence();
      return;
    }
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      if (isBrowserFullscreen()) showImmersiveFigure();
      else focusFigure();
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
    document.body.classList.toggle("is-browser-fullscreen", fs);
    if (fs) {
      if (layout.mode === "expanded") applyLayout();
      return;
    }
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
  applyLayout();

  el.uploadBtn.addEventListener("click", () => el.pdfInput.click());
  if (el.veilBtn) {
    el.veilBtn.addEventListener("click", () => toggleVeilWindow());
  }
  if (el.cacheDeleteBtn) {
    el.cacheDeleteBtn.addEventListener("click", () => deleteActivePaperCache());
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
