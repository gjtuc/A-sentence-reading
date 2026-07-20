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

  let layoutAnimTimer = 0;

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

  /** @type {{ figures: any[], sentences: any[], figureIndex: number, sentenceIndex: number }} */
  const state = {
    figures: [],
    sentences: [],
    figureIndex: 0,
    sentenceIndex: 0,
  };

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
    sentenceText: document.getElementById("sentenceText"),
    sentenceCount: document.getElementById("sentenceCount"),
    sentenceFrame: document.getElementById("sentenceFrame"),
    figureFrame: document.getElementById("figureFrame"),
    stageBadge: document.getElementById("stageBadge"),
    figPrev: document.getElementById("figPrev"),
    figNext: document.getElementById("figNext"),
    sentPrev: document.getElementById("sentPrev"),
    sentNext: document.getElementById("sentNext"),
  };

  function clamp(i, n) {
    if (n <= 0) return 0;
    return ((i % n) + n) % n;
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
    if (layout.fullscreen) return;

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
    state.figureIndex = clamp(state.figureIndex + delta, state.figures.length);
    render();
  }

  function advanceSentence(delta) {
    if (!state.sentences.length) return;
    state.sentenceIndex = clamp(state.sentenceIndex + delta, state.sentences.length);
    render();
  }

  function figLabel() {
    const nF = state.figures.length;
    return nF ? `Fig ${state.figureIndex + 1} / ${nF}` : "Fig — / —";
  }

  function render() {
    const nS = state.sentences.length;
    const fig = state.figures.length ? state.figures[state.figureIndex] : null;
    const sent = nS ? state.sentences[state.sentenceIndex] : null;
    const label = figLabel();

    el.figureCount.textContent = label;
    el.figureCountCollapsed.textContent = label;
    el.sentenceCount.textContent = nS
      ? `Sent ${state.sentenceIndex + 1} / ${nS}`
      : "Sent — / —";

    if (fig) {
      el.figureImage.src = fig.image_src;
      el.figureImage.alt = fig.caption || fig.id;
      el.figureCaption.textContent = fig.caption || "";
      el.figureCaption.hidden = !fig.caption;
    } else {
      el.figureImage.removeAttribute("src");
      el.figureCaption.textContent = "그림 없음";
      el.figureCaption.hidden = false;
    }

    el.sentenceText.textContent = sent
      ? sent.text
      : "문장이 없습니다. mock 세션을 불러오세요.";
  }

  async function loadMock() {
    const res = await fetch("/api/session/mock");
    if (!res.ok) throw new Error("mock session failed");
    const data = await res.json();
    state.figures = data.figures || [];
    state.sentences = data.sentences || [];
    state.figureIndex = data.figure_index || 0;
    state.sentenceIndex = data.sentence_index || 0;
    el.stageBadge.textContent = `skeleton · mock · ${data.title || ""}`;
    render();
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
  el.figureFrame.addEventListener("click", (ev) => {
    ev.preventDefault();
    focusFigure();
  });
  el.figureFrame.setAttribute("tabindex", "0");
  el.figureFrame.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      focusFigure();
    }
  });
  el.sentenceFrame.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      focusSentence();
    }
  });

  function isBrowserFullscreen() {
    return !!(
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.msFullscreenElement
    );
  }

  async function toggleBrowserFullscreen() {
    // WHY: 주소창·북마크 등을 숨겨 읽기 몰입 (Fullscreen API)
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
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    // f = 브라우저 전체화면 (주소창·탭 UI 숨김)
    if (ev.key === "f" || ev.key === "F") {
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
      ev.preventDefault();
      toggleBrowserFullscreen();
      return;
    }

    if (ev.key === "Escape" && layout.fullscreen) {
      ev.preventDefault();
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
    // 브라우저 FS 종료 → 기본 읽기 비율(문장 무스크롤)로
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
  });

  restoreLayout();
  applyLayout();

  loadMock().catch((err) => {
    console.error(err);
    el.stageBadge.textContent = "skeleton · mock load failed";
    el.sentenceText.textContent = "mock 세션을 불러오지 못했습니다.";
  });
})();
