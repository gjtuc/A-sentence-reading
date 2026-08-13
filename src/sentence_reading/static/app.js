/**
 * 프론트 네비 + 그림 크롭 + TTS.
 * INVARIANT: figureIndex 와 sentenceIndex 는 서로 갱신하지 않는다.
 * WHY: 접기/펴기·박스 선택 제스처는 제거하고 TTS·크롭을 우선한다.
 */

(() => {
  "use strict";

  // WHY: index.html head 부팅 가드가 이 플래그로 스크립트 유실(부분 HTML) 여부를 판별
  window.__asrBootOk = true;

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

  /** @type {{ figures: any[], sentences: any[], figureIndex: number, sentenceIndex: number, title: string, sessionId: string | null, translateDigests: Record<string, {en?: string, ko?: string}>, references: {n:number,text:string,doi?:string}[] }} */
  const state = {
    figures: [],
    sentences: [],
    figureIndex: 0,
    sentenceIndex: 0,
    title: "",
    sessionId: null,
    // WHY: design/40 — 섹션 번역 정리본 (되새김질)
    translateDigests: {},
    // WHY: design/41 — References
    references: [],
    // WHY: design/45 — 백그라운드 번역 중
    translatePending: false,
  };

  // WHY: design/45 — 보고 있는 문장 KO 스냅샷 (데이터는 뒤에서 갱신)
  let frozenKoSentenceId = null;
  let frozenKoText = null;

  /** @type {"boot" | "mock" | "loading" | "ready" | "error"} */
  let uiPhase = "boot";

  /**
   * 그림 전체화면 드래그 크롭 확대.
   * norm: 원본 이미지 대비 0~1 사각형 — ↑글 갔다 ↓그림 돌아와도 유지.
   * 확대 중 드래그 = 팬 (마우스 대비 2배 이동).
   * @type {{ active: boolean, norm: { x: number, y: number, w: number, h: number } | null }}
   */
  const cropZoom = { active: false, norm: null };
  /** 팬 속도: 마우스 1px → 이미지 2px (viewport 기준). */
  const CROP_PAN_SPEED = 2;

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
    sentenceKo: document.getElementById("sentenceKo"),
    sentenceKoFrame: document.getElementById("sentenceKoFrame"),
    sentenceBilingual: document.getElementById("sentenceBilingual"),
    translateBtn: document.getElementById("translateBtn"),
    sectionReviewBtn: document.getElementById("sectionReviewBtn"),
    sttPracticeBtn: document.getElementById("sttPracticeBtn"),
    sttPracticePanel: document.getElementById("sttPracticePanel"),
    sttStatus: document.getElementById("sttStatus"),
    sttHeard: document.getElementById("sttHeard"),
    sttDiff: document.getElementById("sttDiff"),
    sentenceCount: document.getElementById("sentenceCount"),
    sentenceFrame: document.getElementById("sentenceFrame"),
    figRefHints: document.getElementById("figRefHints"),
    citeRefHints: document.getElementById("citeRefHints"),
    citeRefPanel: document.getElementById("citeRefPanel"),
    citeRefPanelLabel: document.getElementById("citeRefPanelLabel"),
    citeRefPanelText: document.getElementById("citeRefPanelText"),
    citeRefPanelStatus: document.getElementById("citeRefPanelStatus"),
    citeRefOpenBtn: document.getElementById("citeRefOpenBtn"),
    citeRefCloseBtn: document.getElementById("citeRefCloseBtn"),
    figureFrame: document.getElementById("figureFrame"),
    stageBadge: document.getElementById("stageBadge"),
    figPrev: document.getElementById("figPrev"),
    figNext: document.getElementById("figNext"),
    sentPrev: document.getElementById("sentPrev"),
    sentNext: document.getElementById("sentNext"),
    pdfInput: document.getElementById("pdfInput"),
    uploadBtn: document.getElementById("uploadBtn"),
    uploadCancelBtn: document.getElementById("uploadCancelBtn"),
    guideOutsideSlot: document.getElementById("guideOutsideSlot"),
    guideBtn: document.getElementById("guideBtn"),
    guideDialog: document.getElementById("guideDialog"),
    guideDialogClose: document.getElementById("guideDialogClose"),
    guideNestCheck: document.getElementById("guideNestCheck"),
    guideShowHintsCheck: document.getElementById("guideShowHintsCheck"),
    shadowingPracticeCheck: document.getElementById("shadowingPracticeCheck"),
    shadowingPracticeHint: document.getElementById("shadowingPracticeHint"),
    shadowingChunksBanner: document.getElementById("shadowingChunksBanner"),
    shadowingChunksMsg: document.getElementById("shadowingChunksMsg"),
    shadowingChunksRetry: document.getElementById("shadowingChunksRetry"),
    shadowingPracticeBtn: document.getElementById("shadowingPracticeBtn"),
    shadowingPracticeDialog: document.getElementById("shadowingPracticeDialog"),
    shadowingPracticeClose: document.getElementById("shadowingPracticeClose"),
    shadowingPracticeMeta: document.getElementById("shadowingPracticeMeta"),
    shadowingPracticePrompt: document.getElementById("shadowingPracticePrompt"),
    shadowingPracticeStatus: document.getElementById("shadowingPracticeStatus"),
    shadowingPracticeNext: document.getElementById("shadowingPracticeNext"),
    shadowingPracticeSkip: document.getElementById("shadowingPracticeSkip"),
    shadowingPracticeRetry: document.getElementById("shadowingPracticeRetry"),
    shadowingPracticeReplay: document.getElementById("shadowingPracticeReplay"),
    shadowingPracticeContinue: document.getElementById("shadowingPracticeContinue"),
    sentenceHint: document.getElementById("sentenceHint"),
    figureHint: document.getElementById("figureHint"),
    headerMoreBtn: document.getElementById("headerMoreBtn"),
    headerMoreMenu: document.getElementById("headerMoreMenu"),
    headerMore: document.getElementById("headerMore"),
    libraryBtn: document.getElementById("libraryBtn"),
    libraryDialog: document.getElementById("libraryDialog"),
    libraryList: document.getElementById("libraryList"),
    libraryStatus: document.getElementById("libraryStatus"),
    libraryRefreshBtn: document.getElementById("libraryRefreshBtn"),
    libraryDialogClose: document.getElementById("libraryDialogClose"),
    authLoginBtn: document.getElementById("authLoginBtn"),
    authLogoutBtn: document.getElementById("authLogoutBtn"),
    authAccountBtn: document.getElementById("authAccountBtn"),
    usageBtn: document.getElementById("usageBtn"),
    usageDialog: document.getElementById("usageDialog"),
    usageDialogBody: document.getElementById("usageDialogBody"),
    usageDialogNote: document.getElementById("usageDialogNote"),
    usageDialogClose: document.getElementById("usageDialogClose"),
    authUserLabel: document.getElementById("authUserLabel"),
    cloudUrlLink: document.getElementById("cloudUrlLink"),
    authDialog: document.getElementById("authDialog"),
    authDialogTitle: document.getElementById("authDialogTitle"),
    authDialogHint: document.getElementById("authDialogHint"),
    authDialogStatus: document.getElementById("authDialogStatus"),
    authDialogClose: document.getElementById("authDialogClose"),
    accessWaitingPanel: document.getElementById("accessWaitingPanel"),
    accessWaitingHint: document.getElementById("accessWaitingHint"),
    accessWaitingStatus: document.getElementById("accessWaitingStatus"),
    accessInviteInput: document.getElementById("accessInviteInput"),
    accessInviteSubmit: document.getElementById("accessInviteSubmit"),
    accessWaitingRefresh: document.getElementById("accessWaitingRefresh"),
    accessWaitingLogout: document.getElementById("accessWaitingLogout"),
    authProviderStack: document.getElementById("authProviderStack"),
    authKakaoBtn: document.getElementById("authKakaoBtn"),
    authGoogleBtn: document.getElementById("authGoogleBtn"),
    authEmailToggleBtn: document.getElementById("authEmailToggleBtn"),
    authEmailPanel: document.getElementById("authEmailPanel"),
    authEmailInput: document.getElementById("authEmailInput"),
    authEmailMagicBtn: document.getElementById("authEmailMagicBtn"),
    authLinkPanel: document.getElementById("authLinkPanel"),
    authLinkList: document.getElementById("authLinkList"),
    authLinkKakaoBtn: document.getElementById("authLinkKakaoBtn"),
    authLinkGoogleBtn: document.getElementById("authLinkGoogleBtn"),
    authLinkEmailBtn: document.getElementById("authLinkEmailBtn"),
    googleSignInMount: document.getElementById("googleSignInMount"),
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
    /** @type {{ queue: string[], entries: {sid:string,voice:object}[], i: number, gen: number, btn: HTMLElement|null, paused?: boolean, actionsEl?: HTMLElement|null, statusEl?: HTMLElement|null } | null} */
    voiceSeq: null,
    voiceSeqGen: 0,
    /** 되새김질 안에서 재녹음 중인 문장 id (노트 boundSentenceId 와 별개) */
    reviewRecordSid: null,
    /** @type {{ sid: string, ta: HTMLTextAreaElement, section: string, pk: string } | null} */
    flowEdit: null,
    /** design/56 — flow 세그먼트 키보드 포커스 인덱스 */
    flowSegIndex: 0,
  };

  const TTS_STORAGE_KEY = "asr.tts.v2";
  const TRANSLATE_STORAGE_BASE = "asr.translate.v1";
  // WHY: design/53 — 되새김질(섹션 경계 리뷰) 사용자 on/off · 기본 켜짐(기존 UX 유지)
  const SECTION_REVIEW_STORAGE_BASE = "asr.sectionReview.v1";
  // WHY: design/59 — Guide 헤더 밖(기본) vs ⋯ 안 · UID별 키
  const GUIDE_STORAGE_BASE = "asr.guide.v1";
  // WHY: design/79 — shadowing opt-in; default OFF; uid-scoped like section review.
  const SHADOWING_STORAGE_BASE = "asr.shadowing.v1";
  const shadowingPrefs = { enabled: false, serverAvailable: false };

  /** @type {{ enabled: boolean, mode: "pipeline" | "simple" }} */
  // WHY: design/36 — 기본 pipeline(초안→감수→윤문); simple은 35 호환
  const translatePrefs = { enabled: false, mode: "pipeline" };
  /** @type {{ enabled: boolean }} */
  const sectionReviewPrefs = { enabled: true };
  /** @type {{ nestInMore: boolean, showPanelHints: boolean }} */
  // WHY: design/59·60 — Guide 자리 + 패널 단축키 줄(기본 숨김)
  const guidePrefs = { nestInMore: false, showPanelHints: false };
  /** @type {AbortController | null} */
  let translateAbort = null;
  /** @type {string | null} */
  let sttBoundKey = null;
  /** @type {ReturnType<typeof window.AsrSttPractice.create> | null} */
  let sttPractice = null;
  /** @type {Promise<void> | null} */
  let sttInitPromise = null;

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

  /** 현재 크롭 확대의 화면 스케일 (팬 환산용). */
  function getCropZoomMetrics() {
    if (!cropZoom.active || !cropZoom.norm) return null;
    const vp = el.figureViewport;
    const img = el.figureImage;
    const n = cropZoom.norm;
    if (!vp || !img || !img.naturalWidth) return null;
    const vw = vp.clientWidth;
    const vh = vp.clientHeight;
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    const cw = Math.max(n.w * nw, 1);
    const ch = Math.max(n.h * nh, 1);
    const s = Math.min(vw / cw, vh / ch);
    if (!(s > 0)) return null;
    return { s, nw, nh };
  }

  /**
   * 확대 창을 이미지 위에서 이동 (구글 지도식 팬).
   * dx/dy = 포인터 이동(px). 이미지 이동량은 CROP_PAN_SPEED 배.
   */
  function panCropBy(dx, dy) {
    const m = getCropZoomMetrics();
    if (!m || !cropZoom.norm) return;
    const n = cropZoom.norm;
    // 손가락을 오른쪽으로 → 이미지도 오른쪽 (보이는 영역은 왼쪽으로)
    n.x -= (CROP_PAN_SPEED * dx) / (m.s * m.nw);
    n.y -= (CROP_PAN_SPEED * dy) / (m.s * m.nh);
    n.x = Math.max(0, Math.min(1 - n.w, n.x));
    n.y = Math.max(0, Math.min(1 - n.h, n.y));
    applyCropZoom();
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
          ? "드래그: 크롭 확대 · 확대 중 드래그: 팬(2×) · 클릭: 축소 · Esc: 종료"
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

  function persistReadingProgress() {
    // WHY: M5 — 문장/그림 위치 localStorage (design/21)
    if (typeof AsrProgress === "undefined" || !AsrProgress) return;
    const p = papers[activePaperIndex];
    if (!p || isMockPaper(p)) return;
    AsrProgress.saveProgress(p, state.figureIndex, state.sentenceIndex);
  }

  function advanceFigure(delta) {
    if (!state.figures.length) return;
    clearCropZoom();
    state.figureIndex = clamp(state.figureIndex + delta, state.figures.length);
    render();
    snapshotActivePaper();
    persistReadingProgress();
    void prefetchFigureWindow();
  }

  /** Fig. N 칩 — 문장 인덱스는 그대로 (design/28). */
  function goToFigureIndex(index) {
    if (!state.figures.length) return;
    const i = Math.max(0, Math.min(index | 0, state.figures.length - 1));
    if (i === state.figureIndex) return;
    clearCropZoom();
    state.figureIndex = i;
    render();
    snapshotActivePaper();
    persistReadingProgress();
    void prefetchFigureWindow();
  }

  /**
   * design/129 — fill current±1 image_src from /figures/window (no downscale).
   * Fail-closed: leave stubs empty on error (render shows 이미지 없음).
   */
  async function prefetchFigureWindow() {
    const sid = state.sessionId;
    if (!sid || !state.figures.length) return;
    const center = state.figureIndex | 0;
    try {
      const res = await fetch(
        "/api/session/" +
          encodeURIComponent(sid) +
          "/figures/window?center=" +
          encodeURIComponent(String(center)) +
          "&span=1"
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) return;
      if (state.sessionId !== sid) return;
      const rows = Array.isArray(data.figures) ? data.figures : [];
      for (const row of rows) {
        if (!row || typeof row !== "object") continue;
        const src = String(row.image_src || "").trim();
        if (!src) continue;
        let idx = row.index;
        if (typeof idx !== "number") idx = parseInt(idx, 10);
        if (
          Number.isFinite(idx) &&
          idx >= 0 &&
          idx < state.figures.length
        ) {
          state.figures[idx].image_src = src;
          continue;
        }
        const id = String(row.id || "").trim();
        if (!id) continue;
        for (const f of state.figures) {
          if (f && f.id === id) {
            f.image_src = src;
            break;
          }
        }
      }
      render();
      snapshotActivePaper();
    } catch (_) {
      /* leave stubs */
    }
  }

  /** @type {{ n: number, text: string, doi: string } | null} */
  let citePanelEntry = null;

  function closeCiteRefPanel() {
    citePanelEntry = null;
    if (el.citeRefPanel) el.citeRefPanel.hidden = true;
    if (el.citeRefPanelText) el.citeRefPanelText.textContent = "";
    if (el.citeRefPanelStatus) el.citeRefPanelStatus.textContent = "";
    if (el.citeRefPanelLabel) el.citeRefPanelLabel.textContent = "[—]";
  }

  function openCiteRefPanel(entry) {
    if (!el.citeRefPanel || !entry) return;
    citePanelEntry = entry;
    el.citeRefPanel.hidden = false;
    if (el.citeRefPanelLabel) {
      el.citeRefPanelLabel.textContent = "[" + entry.n + "]";
    }
    if (el.citeRefPanelText) {
      el.citeRefPanelText.textContent = entry.text || "";
    }
    if (el.citeRefPanelStatus) el.citeRefPanelStatus.textContent = "";
  }

  /**
   * design/41 — 원문 열기. 인덱스 불변.
   */
  async function openCiteResolvedUrl() {
    if (!citePanelEntry || !el.citeRefOpenBtn) return;
    if (el.citeRefPanelStatus) el.citeRefPanelStatus.textContent = "찾는 중…";
    el.citeRefOpenBtn.disabled = true;
    try {
      const res = await fetch("/api/cite/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ text: citePanelEntry.text || "" }),
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!data.ok || !data.url) {
        if (el.citeRefPanelStatus) {
          el.citeRefPanelStatus.textContent =
            data.error === "empty" ? "문헌 텍스트 없음" : "원문을 찾지 못함";
        }
        return;
      }
      if (el.citeRefPanelStatus) {
        const src = data.source || "";
        el.citeRefPanelStatus.textContent =
          src === "doi_in_text"
            ? "DOI로 열기"
            : src === "crossref"
              ? "Crossref 매칭"
              : src === "scholar_fallback"
                ? "Scholar 검색"
                : "";
      }
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (_) {
      if (el.citeRefPanelStatus) {
        el.citeRefPanelStatus.textContent = "네트워크 오류";
      }
    } finally {
      el.citeRefOpenBtn.disabled = false;
    }
  }

  function renderCiteRefHints(sent) {
    if (!el.citeRefHints) return;
    el.citeRefHints.innerHTML = "";
    if (
      !sent ||
      !state.references.length ||
      typeof AsrCiteRefs === "undefined" ||
      !AsrCiteRefs
    ) {
      el.citeRefHints.hidden = true;
      closeCiteRefPanel();
      return;
    }
    const rows = AsrCiteRefs.hintsForSentence(
      sent.text || "",
      state.references
    );
    if (!rows.length) {
      el.citeRefHints.hidden = true;
      closeCiteRefPanel();
      return;
    }
    el.citeRefHints.hidden = false;
    rows.forEach(function (row) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cite-ref-chip";
      if (citePanelEntry && citePanelEntry.n === row.n) {
        btn.classList.add("is-current");
      }
      btn.textContent = "[" + row.n + "]";
      btn.title = "참고문헌 [" + row.n + "] 보기";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        // INVARIANT: sentence_index / figure_index 불변
        openCiteRefPanel(row);
        renderCiteRefHints(sent);
      });
      el.citeRefHints.appendChild(btn);
    });
  }

  function renderFigRefHints(sent) {
    if (!el.figRefHints) return;
    el.figRefHints.innerHTML = "";
    if (
      !sent ||
      !state.figures.length ||
      typeof AsrFigRefs === "undefined" ||
      !AsrFigRefs
    ) {
      el.figRefHints.hidden = true;
      return;
    }
    const rows = AsrFigRefs.hintsForSentence(sent.text || "", state.figures);
    if (!rows.length) {
      el.figRefHints.hidden = true;
      return;
    }
    el.figRefHints.hidden = false;
    rows.forEach(function (row) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "fig-ref-chip";
      if (row.figure_index === state.figureIndex) {
        btn.classList.add("is-current");
      }
      btn.textContent = row.ref + " →";
      btn.title = "그림 " + (row.figure_index + 1) + "으로 이동";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        goToFigureIndex(row.figure_index);
      });
      el.figRefHints.appendChild(btn);
    });
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
    // WHY: design/45 — 문장 이동 시 스냅샷 해제 → 최신 text_ko 표시
    frozenKoSentenceId = null;
    frozenKoText = null;
    const next = state.sentences[state.sentenceIndex];
    const nextSec = next && next.section ? String(next.section) : "";
    // WHY: 앞으로 갈 때만 섹션 경계 → 직전 구간 되새김질 (design/17 · 53 on일 때만)
    const crossedForward =
      delta > 0 &&
      prevSec &&
      nextSec &&
      prevSec !== nextSec &&
      state.sentenceIndex !== prevIdx;
    render();
    snapshotActivePaper();
    persistReadingProgress();
    if (crossedForward && sectionReviewPrefs.enabled) {
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
    // design/132 — cancel only while an ingest is in flight.
    if (el.uploadCancelBtn) {
      el.uploadCancelBtn.hidden = !on;
      el.uploadCancelBtn.disabled = !on;
    }
  }

  // design/132 — cooperative cancel for web ingest poll loop.
  let ingestCancelRequested = false;
  let ingestActiveJobId = null;

  async function requestIngestCancel() {
    ingestCancelRequested = true;
    const jobId = ingestActiveJobId;
    if (!jobId) return;
    try {
      const res = await fetch(
        `/api/ingest/jobs/${encodeURIComponent(jobId)}/cancel`,
        { method: "POST", credentials: "same-origin" }
      );
      const body = await res.json().catch(() => ({}));
      if (res.status === 409 || body.error === "cancel_too_late") {
        // Product: let it finish — clear cancel so poll continues.
        ingestCancelRequested = false;
        setUploadStatus(
          body.message || "거의 끝나 취소할 수 없습니다. 그대로 완료됩니다.",
          "busy"
        );
      }
    } catch (_) {
      // Local flag still stops the poll; server wipe is best-effort.
    }
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
    p.translateDigests = state.translateDigests || {};
    p.references = state.references || [];
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
    state.translateDigests = p.translateDigests || {};
    state.references = p.references || [];
    state.translatePending = !!p.translatePending;
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

  /**
   * 크롬식 탭 드래그: 클론이 커서를 따라 가로로 미끄러지고, 원본 자리엔 placeholder.
   * pointerdown 직후 document 리스너 등록 (capture 끊김·pointer-events 이슈 회피).
   * @type {{
   *   pointerId: number,
   *   paperKey: string,
   *   startX: number,
   *   startY: number,
   *   offsetX: number,
   *   offsetY: number,
   *   width: number,
   *   height: number,
   *   barTop: number,
   *   dragging: boolean,
   *   fromSlot: number,
   *   hoverSlot: number,
   *   sourceBtn: HTMLElement | null,
   *   ghost: HTMLElement | null,
   * } | null}
   */
  let tabDrag = null;
  let suppressTabClickUntil = 0;
  const TAB_DRAG_PX = 4;

  function cssEscapeKey(key) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(key);
    return String(key).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function cleanupTabDragDocListeners() {
    document.removeEventListener("pointermove", onTabPointerMoveDoc, true);
    document.removeEventListener("pointerup", onTabPointerUpDoc, true);
    document.removeEventListener("pointercancel", onTabPointerUpDoc, true);
  }

  function removeTabPlaceholder() {
    if (!el.paperTabs) return;
    el.paperTabs
      .querySelectorAll(".paper-tab-placeholder")
      .forEach((n) => n.remove());
  }

  function removeTabGhost() {
    if (!tabDrag || !tabDrag.ghost) return;
    tabDrag.ghost.remove();
    tabDrag.ghost = null;
  }

  /** real 슬롯 fromSlot → toSlot (placeholder 기준 insert 인덱스). */
  function reorderRealSlot(fromSlot, toSlot) {
    const real = realPaperIndices();
    if (fromSlot === toSlot) return false;
    if (fromSlot < 0 || toSlot < 0 || toSlot >= real.length) return false;
    const activeRef = papers[activePaperIndex];
    const fromIndex = real[fromSlot];
    const [item] = papers.splice(fromIndex, 1);
    const realAfter = papers
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => !isMockPaper(p))
      .map(({ i }) => i);
    let insertAt;
    if (toSlot >= realAfter.length) {
      insertAt = papers.length;
    } else {
      insertAt = realAfter[toSlot];
    }
    papers.splice(insertAt, 0, item);
    if (activeRef) {
      const idx = papers.indexOf(activeRef);
      if (idx >= 0) activePaperIndex = idx;
    }
    return true;
  }

  function positionTabGhost(clientX) {
    if (!tabDrag || !tabDrag.ghost) return;
    // WHY: 크롬처럼 세로로 안 빼고 탭 줄 높이에 고정 · 가로만 따라감
    const left = clientX - tabDrag.offsetX;
    tabDrag.ghost.style.left = `${left}px`;
    tabDrag.ghost.style.top = `${tabDrag.barTop}px`;
  }

  function movePlaceholderToSlot(slot) {
    const bar = el.paperTabs;
    if (!bar || !tabDrag) return;
    const ph = bar.querySelector(".paper-tab-placeholder");
    if (!ph) return;
    const others = [...bar.children].filter(
      (n) =>
        n !== ph &&
        !n.classList.contains("is-tab-source-hidden") &&
        n.classList.contains("paper-tab")
    );
    if (slot >= others.length) {
      const last = others[others.length - 1];
      if (last) last.after(ph);
      else bar.appendChild(ph);
    } else {
      others[slot].before(ph);
    }
    tabDrag.hoverSlot = slot;
  }

  function hoverSlotFromPointer(clientX) {
    const bar = el.paperTabs;
    if (!bar) return 0;
    const slots = [...bar.children].filter(
      (n) =>
        n.classList.contains("paper-tab-placeholder") ||
        (n.classList.contains("paper-tab") &&
          !n.classList.contains("is-tab-source-hidden"))
    );
    if (!slots.length) return 0;
    for (let i = 0; i < slots.length; i++) {
      const r = slots[i].getBoundingClientRect();
      if (clientX < r.left + r.width / 2) return i;
    }
    return slots.length - 1;
  }

  function beginTabFloat() {
    if (!tabDrag || tabDrag.dragging || !tabDrag.sourceBtn) return;
    const btn = tabDrag.sourceBtn;
    const rect = btn.getBoundingClientRect();
    const barRect = el.paperTabs
      ? el.paperTabs.getBoundingClientRect()
      : rect;
    const real = realPaperIndices();
    const fromIndex = findPaperIndexByKey(tabDrag.paperKey);
    const fromSlot = real.indexOf(fromIndex);

    tabDrag.width = rect.width;
    tabDrag.height = rect.height;
    tabDrag.barTop = barRect.top + (barRect.height - rect.height) / 2;
    tabDrag.dragging = true;
    tabDrag.fromSlot = fromSlot;
    tabDrag.hoverSlot = fromSlot;

    removeTabPlaceholder();
    const ph = document.createElement("div");
    ph.className = "paper-tab-placeholder";
    ph.setAttribute("aria-hidden", "true");
    ph.style.width = `${rect.width}px`;
    ph.style.height = `${rect.height}px`;
    ph.style.flex = `0 0 ${rect.width}px`;
    btn.before(ph);
    btn.classList.add("is-tab-source-hidden");

    const ghost = btn.cloneNode(true);
    ghost.removeAttribute("id");
    ghost.classList.add("is-tab-float");
    ghost.classList.remove("is-tab-source-hidden");
    ghost.setAttribute("aria-hidden", "true");
    ghost.style.position = "fixed";
    ghost.style.left = `${rect.left}px`;
    ghost.style.top = `${tabDrag.barTop}px`;
    ghost.style.width = `${rect.width}px`;
    ghost.style.height = `${rect.height}px`;
    ghost.style.zIndex = "10000";
    ghost.style.margin = "0";
    ghost.style.pointerEvents = "none";
    document.body.appendChild(ghost);
    tabDrag.ghost = ghost;
  }

  function abortTabFloatVisual() {
    if (!tabDrag) return;
    if (tabDrag.sourceBtn) {
      tabDrag.sourceBtn.classList.remove("is-tab-source-hidden");
    }
    removeTabGhost();
    removeTabPlaceholder();
    cleanupTabDragDocListeners();
  }

  function endTabDrag(ev) {
    if (!tabDrag) return;
    if (ev && ev.pointerId !== tabDrag.pointerId) return;
    const wasDragging = tabDrag.dragging;
    const key = tabDrag.paperKey;
    const fromSlot = tabDrag.fromSlot;
    const toSlot = tabDrag.hoverSlot;
    abortTabFloatVisual();
    tabDrag = null;
    if (!wasDragging) {
      const idx = findPaperIndexByKey(key);
      if (idx >= 0) activatePaper(idx);
      return;
    }
    suppressTabClickUntil = Date.now() + 400;
    if (
      fromSlot >= 0 &&
      toSlot >= 0 &&
      toSlot !== fromSlot &&
      reorderRealSlot(fromSlot, toSlot)
    ) {
      /* order committed */
    }
    renderPaperTabs();
    updatePaperTabChrome();
  }

  function onTabPointerMoveDoc(ev) {
    if (!tabDrag || ev.pointerId !== tabDrag.pointerId) return;
    if (!tabDrag.dragging) {
      const dx = ev.clientX - tabDrag.startX;
      const dy = ev.clientY - tabDrag.startY;
      if (Math.hypot(dx, dy) < TAB_DRAG_PX) return;
      beginTabFloat();
    }
    if (!tabDrag || !tabDrag.dragging) return;
    ev.preventDefault();
    positionTabGhost(ev.clientX);
    const slot = hoverSlotFromPointer(ev.clientX);
    if (slot !== tabDrag.hoverSlot) movePlaceholderToSlot(slot);
  }

  function onTabPointerUpDoc(ev) {
    endTabDrag(ev);
  }

  function renderPaperTabs() {
    const bar = el.paperTabs;
    if (!bar) return;
    if (tabDrag) {
      abortTabFloatVisual();
      tabDrag = null;
    }
    bar.innerHTML = "";
    const real = papers
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => !isMockPaper(p));
    // WHY: 실논문 1개여도 ×로 닫을 수 있게 탭 줄 표시 (design/34)
    if (real.length < 1) {
      bar.hidden = true;
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
      btn.title = `${slot + 1}. ${stripTags(p.title) || "Untitled"} (키 ${slot + 1} · 드래그로 순서 · × 닫기)`;
      const label = document.createElement("span");
      label.className = "paper-tab-label";
      label.innerHTML = `<span class="paper-tab-num">${slot + 1}</span>${shortTitle(p.title)}`;
      const closeBtn = document.createElement("span");
      closeBtn.className = "paper-tab-close";
      closeBtn.setAttribute("role", "button");
      closeBtn.setAttribute("tabindex", "0");
      closeBtn.setAttribute("aria-label", "탭 닫기");
      closeBtn.title = "탭 닫기 (진행·노트 저장)";
      closeBtn.textContent = "×";
      closeBtn.addEventListener("pointerdown", (ev) => {
        // WHY: 탭 드래그/활성화와 분리 · button 중첩 금지라 span[role=button]
        ev.preventDefault();
        ev.stopPropagation();
      });
      closeBtn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        void closePaperTab(i);
      });
      closeBtn.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          ev.stopPropagation();
          void closePaperTab(i);
        }
      });
      btn.appendChild(label);
      btn.appendChild(closeBtn);
      btn.addEventListener("pointerdown", (ev) => {
        if (ev.button !== 0) return;
        if (ev.target && ev.target.closest && ev.target.closest(".paper-tab-close")) {
          return;
        }
        ev.preventDefault();
        const rect = btn.getBoundingClientRect();
        if (tabDrag) {
          abortTabFloatVisual();
          tabDrag = null;
        }
        tabDrag = {
          pointerId: ev.pointerId,
          paperKey: key,
          startX: ev.clientX,
          startY: ev.clientY,
          offsetX: ev.clientX - rect.left,
          offsetY: ev.clientY - rect.top,
          width: rect.width,
          height: rect.height,
          barTop: rect.top,
          dragging: false,
          fromSlot: slot,
          hoverSlot: slot,
          sourceBtn: btn,
          ghost: null,
        };
        document.addEventListener("pointermove", onTabPointerMoveDoc, true);
        document.addEventListener("pointerup", onTabPointerUpDoc, true);
        document.addEventListener("pointercancel", onTabPointerUpDoc, true);
      });
      btn.addEventListener("click", (ev) => {
        if (ev.target && ev.target.closest && ev.target.closest(".paper-tab-close")) {
          return;
        }
        if (Date.now() < suppressTabClickUntil) {
          ev.preventDefault();
          ev.stopPropagation();
          return;
        }
        activatePaper(i);
      });
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
      stopTts();
      if (noteUi.open) flushNoteSave();
      snapshotActivePaper();
      persistReadingProgress();
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

  /**
   * 논문 탭 × — 탭 범위 저장 후 닫기 (보관/GCS 삭제가 아님).
   * WHY: 진행·노트만 저장. TTS/테마는 전역이라 손대지 않음 (design/34).
   * @param {number} paperIndex papers[] 인덱스
   */
  async function closePaperTab(paperIndex) {
    if (
      paperIndex < 0 ||
      paperIndex >= papers.length ||
      isMockPaper(papers[paperIndex])
    ) {
      return;
    }
    const closingActive = paperIndex === activePaperIndex;
    if (closingActive) {
      stopTts();
      if (noteUi.open) flushNoteSave();
      snapshotActivePaper();
      persistReadingProgress();
      if (noteUi.open) {
        noteUi.open = false;
        if (el.notePanel) el.notePanel.hidden = true;
      }
    } else {
      // 비활성 탭: 진행은 마지막 activate 때 이미 localStorage 에 있음
      // (노트는 활성 탭 키에만 묶이므로 여기서 flush 불필요)
    }

    papers.splice(paperIndex, 1);
    if (activePaperIndex > paperIndex) {
      activePaperIndex -= 1;
    } else if (activePaperIndex === paperIndex) {
      activePaperIndex = Math.min(paperIndex, papers.length - 1);
    }

    const reals = realPaperIndices();
    if (!reals.length) {
      papers = [];
      activePaperIndex = 0;
      await loadMock();
      renderPaperTabs();
      updateCacheDeleteBtn();
      return;
    }

    if (closingActive || activePaperIndex < 0 || isMockPaper(papers[activePaperIndex])) {
      const prefer =
        reals.find((i) => i >= paperIndex) ?? reals[reals.length - 1];
      activePaperIndex = prefer;
      hydrateStateFromPaper(papers[activePaperIndex]);
      uiPhase = "ready";
      render();
      if (layout.fullscreen) applyCropZoom();
    }
    renderPaperTabs();
    updatePaperTabChrome();
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

  /**
   * design/45 — 백그라운드 번역 중간 결과 병합 (인덱스·포커스 유지).
   * @param {object} data
   */
  function mergeTranslateProgress(data) {
    if (!data || !Array.isArray(data.sentences)) return;
    const paper = papers[activePaperIndex];
    state.sentences = data.sentences;
    state.figures = Array.isArray(data.figures) ? data.figures : state.figures;
    state.translateDigests = data.translate_digests || state.translateDigests;
    state.translatePending = !!data.translate_pending;
    if (typeof data.title === "string" && data.title) state.title = data.title;
    if (paper) {
      paper.sentences = state.sentences;
      paper.figures = state.figures;
      paper.translateDigests = state.translateDigests;
      paper.translatePending = state.translatePending;
      if (data.cache_id) paper.cacheId = data.cache_id;
    }
    // 현재 문장만 다시 그림/힌트 — KO 는 frozen 이면 refresh 가 스냅샷 유지
    render();
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
      contentHash: data.content_hash || null,
      // WHY: design/40 — ingest 섹션 요지 (캐시/세션 동일 키)
      translateDigests: data.translate_digests || {},
      // WHY: design/41 — References
      references: data.references || [],
      translatePending: !!data.translate_pending,
      isMock: phase === "mock",
      crop: emptyCrop(),
    };

    // WHY: mock 제외 — 저장된 읽기 위치가 있으면 서버 기본(0)보다 우선 (design/21·123)
    // EDGE: 이상 저장값 → papers 에 넣기 전에 throw (성공 UI 금지 · fail-closed).
    if (
      phase !== "mock" &&
      typeof AsrProgress !== "undefined" &&
      AsrProgress
    ) {
      const outcome = AsrProgress.applyStoredProgress(
        paper,
        paper.figures.length,
        paper.sentences.length,
        { failClosed: progressFailClosedFlag !== false }
      );
      if (outcome && outcome.ok === false) {
        throw new Error(
          (outcome && outcome.message) ||
            (AsrProgress.INVALID_PROGRESS_MSG) ||
            "저장된 읽기 위치가 이 논문과 맞지 않습니다."
        );
      }
    }

    if (phase === "mock" || !asNewTab) {
      papers = [paper];
      activePaperIndex = 0;
    } else {
      snapshotActivePaper();
      // WHY: mock 은 기본 화면용 — 실제 논문이 열리면 탭에서 제거
      papers = papers.filter((p) => !isMockPaper(p));
      const existing = papers.findIndex(
        (p) =>
          (p.sessionId &&
            paper.sessionId &&
            p.sessionId === paper.sessionId) ||
          (p.cacheId && paper.cacheId && p.cacheId === paper.cacheId)
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
      // WHY: design/13+88 — sanitize + unescape escaped <sub> before paint
      let html = sanitizeSentenceHtmlClient(text || "");
      if (window.AsrCiteRefs && AsrCiteRefs.stripCiteMarkersForDisplay) {
        html = AsrCiteRefs.stripCiteMarkersForDisplay(html);
      }
      el.sentenceText.innerHTML = html;
    }
  }

  /** design/88 — allowlist sub/sup/i/em; decode one &lt;sub&gt; layer; drop other tags. */
  function sanitizeSentenceHtmlClient(raw) {
    let s = String(raw || "");
    if (!s) return "";
    // EDGE: double-escaped markup shows as visible "<sub>" if painted as text/entities.
    if (/&lt;\/?(?:sub|sup|i|em)\b/i.test(s)) {
      const ta = document.createElement("textarea");
      ta.innerHTML = s;
      s = ta.value;
    }
    if (s.indexOf("<") < 0) {
      const d = document.createElement("div");
      d.textContent = s;
      return d.innerHTML;
    }
    const wrap = document.createElement("div");
    wrap.innerHTML = s;
    const allowed = { SUB: 1, SUP: 1, I: 1, EM: 1 };
    function walk(node) {
      const kids = Array.prototype.slice.call(node.childNodes);
      for (let i = 0; i < kids.length; i++) {
        const child = kids[i];
        if (child.nodeType === 1) {
          const tag = child.tagName;
          if (!allowed[tag]) {
            while (child.firstChild) {
              node.insertBefore(child.firstChild, child);
            }
            node.removeChild(child);
            continue;
          }
          // Strip all attributes (XSS / style injection).
          while (child.attributes && child.attributes.length) {
            child.removeAttribute(child.attributes[0].name);
          }
          walk(child);
        }
      }
    }
    walk(wrap);
    return wrap.innerHTML;
  }

  function setSentenceKoDisplay(text) {
    // design/88 — KO may carry the same allowlisted tags; never leave raw <sub>.
    const raw = text || "";
    if (/<\s*\/?\s*(sub|sup|i|em)\b/i.test(raw) || /&lt;\/?(?:sub|sup|i|em)\b/i.test(raw)) {
      el.sentenceKo.innerHTML = sanitizeSentenceHtmlClient(raw);
    } else {
      el.sentenceKo.textContent = raw;
    }
  }

  function translateStorageKey() {
    const uid = authState.user && authState.user.uid;
    return uid
      ? TRANSLATE_STORAGE_BASE + "." + String(uid)
      : TRANSLATE_STORAGE_BASE;
  }

  function loadTranslatePrefs() {
    try {
      const raw = localStorage.getItem(translateStorageKey());
      if (!raw) {
        translatePrefs.enabled = false;
        translatePrefs.mode = "pipeline";
      } else {
        const data = JSON.parse(raw);
        translatePrefs.enabled = !!data.enabled;
        const m = String(data.mode || "pipeline").toLowerCase();
        translatePrefs.mode = m === "simple" ? "simple" : "pipeline";
      }
    } catch (_) {
      translatePrefs.enabled = false;
      translatePrefs.mode = "pipeline";
    }
    syncTranslateBtn();
  }

  function saveTranslatePrefs() {
    try {
      localStorage.setItem(
        translateStorageKey(),
        JSON.stringify({
          enabled: !!translatePrefs.enabled,
          mode: translatePrefs.mode === "simple" ? "simple" : "pipeline",
        })
      );
    } catch (_) {
      /* ignore quota */
    }
  }

  function syncTranslateBtn() {
    if (!el.translateBtn) return;
    el.translateBtn.setAttribute(
      "aria-pressed",
      translatePrefs.enabled ? "true" : "false"
    );
    el.translateBtn.title = translatePrefs.enabled
      ? "번역 표시 켜짐 (다단계) — 클릭하면 끔"
      : "영→한 다단계 번역 표시 (기본 꺼짐)";
  }

  function setBilingualSplit(on) {
    // WHY: design/39 — 전체·축소 공통 EN|KO 좌우
    if (el.sentenceBilingual) {
      el.sentenceBilingual.classList.toggle("is-split", !!on);
    }
    if (el.sentenceKoFrame) {
      el.sentenceKoFrame.hidden = !on;
    }
  }

  function clearSentenceKo() {
    if (!el.sentenceKo) return;
    el.sentenceKo.textContent = "";
    el.sentenceKo.classList.remove("is-error", "is-loading");
    setBilingualSplit(false);
  }

  function plainSentenceForTranslate(htmlOrText) {
    const d = document.createElement("div");
    d.innerHTML = htmlOrText || "";
    return (d.textContent || "").replace(/\s+/g, " ").trim();
  }

  /** design/49 — KO/STT 표시·기대문에서도 각주 마커 제거 */
  function stripCitesForUi(text) {
    if (window.AsrCiteRefs && AsrCiteRefs.stripCiteMarkersForDisplay) {
      return AsrCiteRefs.stripCiteMarkersForDisplay(text || "");
    }
    return text || "";
  }

  /**
   * 현재 문장 영→한 표시 (design/35·39·40·42·45).
   * ingest 시 저장된 text_ko 만 사용 — live /api/translate 폴백 없음 (design/42).
   * 보고 있는 문장은 frozenKo 스냅샷 유지 (다른 문장 이동 시 최신본).
   * @param {string} plainEn
   */
  async function refreshSentenceKo(plainEn) {
    if (!el.sentenceKo) return;
    if (translateAbort) {
      try {
        translateAbort.abort();
      } catch (_) {
        /* ignore */
      }
      translateAbort = null;
    }
    if (!translatePrefs.enabled) {
      clearSentenceKo();
      return;
    }
    if (!plainEn) {
      clearSentenceKo();
      return;
    }
    const cur = state.sentences[state.sentenceIndex];
    const sid = cur && (cur.id || String(state.sentenceIndex));
    setBilingualSplit(true);
    el.sentenceKo.classList.remove("is-loading");

    // WHY: design/45 — 보고 있는 문장은 읽기 중 바꿔치기 금지
    if (
      sid != null &&
      frozenKoSentenceId != null &&
      String(frozenKoSentenceId) === String(sid) &&
      frozenKoText != null
    ) {
      el.sentenceKo.classList.remove("is-error");
      setSentenceKoDisplay(stripCitesForUi(frozenKoText));
      return;
    }

    const cachedKo = cur && String(cur.text_ko || "").trim();
    if (cachedKo) {
      el.sentenceKo.classList.remove("is-error");
      const shown = stripCitesForUi(cachedKo);
      setSentenceKoDisplay(shown);
      frozenKoSentenceId = sid;
      frozenKoText = shown;
      return;
    }
    // WHY: design/45 — 진행 중이면 「미리 번역 없음」대신 진행 안내
    el.sentenceKo.classList.add("is-error");
    if (state.translatePending) {
      el.sentenceKo.textContent = "번역 진행 중";
    } else {
      el.sentenceKo.textContent = "미리 번역 없음 (파일을 다시 열거나 재분석)";
    }
    frozenKoSentenceId = sid;
    frozenKoText = el.sentenceKo.textContent;
  }

  function sttExpectedPlain() {
    const nS = state.sentences.length;
    if (!nS) return "";
    const sent = state.sentences[state.sentenceIndex];
    if (!sent) return "";
    let body = sent.text || "";
    const lab = sectionLabel(sent.section);
    if (lab) {
      const re = new RegExp(`^${lab}\\s*:\\s*`, "i");
      body = body.replace(re, "");
    }
    return stripCitesForUi(plainSentenceForTranslate(body));
  }

  function sttSentenceKey() {
    const sent = state.sentences[state.sentenceIndex];
    const sid = sent && (sent.id || sent.sentence_id || state.sentenceIndex);
    return String(state.sentenceIndex) + ":" + String(sid);
  }

  /**
   * 브라우저 STT 발음 연습 UI (design/37). 점수 표시 금지.
   * @param {object} u
   */
  function onSttPracticeUpdate(u) {
    if (!el.sttPracticePanel) return;
    el.sttPracticePanel.hidden = false;
    if (el.sttPracticeBtn) {
      el.sttPracticeBtn.setAttribute(
        "aria-pressed",
        u && (u.active || u.uploading) ? "true" : "false"
      );
    }
    if (el.sttStatus) {
      if (u && u.error === "unsupported") {
        el.sttStatus.textContent = u.message || "음성 인식 미지원";
      } else if (u && u.error) {
        el.sttStatus.textContent = u.message || String(u.error);
      } else if (u && u.uploading) {
        el.sttStatus.textContent = u.message || "서버 인식 중…";
      } else if (u && u.active) {
        if (u.mode === "server") {
          el.sttStatus.textContent =
            u.message || "녹음 중… 다시 누르면 중지·서버 인식";
        } else {
          el.sttStatus.textContent = u.interim
            ? "듣는 중… " + u.interim
            : "듣는 중… 영어로 문장을 말해 주세요.";
        }
      } else if (u && u.compare && u.compare.ok) {
        el.sttStatus.textContent =
          "비교 결과 (점수 없음" +
          (u.engine ? " · " + u.engine : "") +
          ")";
      } else if (u && u.compare && u.compare.ok === false) {
        el.sttStatus.textContent =
          u.compare.error === "empty"
            ? "인식·원문이 비어 비교하지 않음"
            : "비교 실패";
      } else if (u && u.message) {
        el.sttStatus.textContent = u.message;
      } else {
        el.sttStatus.textContent = "말하기를 눌러 연습";
      }
    }
    if (el.sttHeard) {
      const heard = (u && (u.heard || u.finalText || u.interim)) || "";
      if (heard && !(u && u.active && !u.finalText && u.mode !== "server")) {
        el.sttHeard.hidden = false;
        el.sttHeard.textContent = "인식: " + heard;
      } else if (u && u.active && u.interim) {
        el.sttHeard.hidden = false;
        el.sttHeard.textContent = "인식 중: " + u.interim;
      } else if (!(u && u.compare && u.compare.ok)) {
        el.sttHeard.hidden = true;
        el.sttHeard.textContent = "";
      }
    }
    if (el.sttDiff) {
      if (
        u &&
        u.compare &&
        u.compare.ok &&
        window.AsrSttPractice &&
        typeof window.AsrSttPractice.renderDiffHtml === "function"
      ) {
        // INVARIANT: score/grade를 DOM에 쓰지 않음
        el.sttDiff.innerHTML = window.AsrSttPractice.renderDiffHtml(
          u.compare.diff || []
        );
      } else if (!(u && (u.active || u.uploading))) {
        el.sttDiff.innerHTML = "";
      }
    }
  }

  function resetSttPracticePanel() {
    if (sttPractice && typeof sttPractice.reset === "function") {
      sttPractice.reset();
    }
    if (el.sttPracticePanel) el.sttPracticePanel.hidden = true;
    if (el.sttPracticeBtn) {
      el.sttPracticeBtn.setAttribute("aria-pressed", "false");
    }
    if (el.sttStatus) el.sttStatus.textContent = "";
    if (el.sttHeard) {
      el.sttHeard.hidden = true;
      el.sttHeard.textContent = "";
    }
    if (el.sttDiff) el.sttDiff.innerHTML = "";
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
      const imgSrc = String(fig.image_src || "").trim();
      const capEn = fig.caption || "";
      const capKo =
        translatePrefs.enabled && String(fig.caption_ko || "").trim()
          ? String(fig.caption_ko).trim()
          : "";
      const capShow = capKo || capEn;
      // design/124 — empty/broken image: keep caption slot, honest message (no fake success).
      if (!imgSrc) {
        clearCropZoom();
        el.figureImage.removeAttribute("src");
        el.figureImage.alt = "";
        el.figureCaption.textContent = capShow
          ? capShow + " · 이미지 없음"
          : "이미지 없음";
        el.figureCaption.hidden = false;
      } else {
        el.figureImage.src = imgSrc;
        el.figureImage.alt = fig.caption || fig.id;
        el.figureCaption.textContent = capShow;
        el.figureCaption.hidden = !capShow;
        if (!el.figureImage._asrErrBound) {
          el.figureImage._asrErrBound = true;
          el.figureImage.addEventListener("error", () => {
            // WHY: broken data URL / network — do not leave blank success chrome.
            el.figureImage.removeAttribute("src");
            const base = (el.figureCaption.textContent || "").replace(
              /\s*·\s*이미지 없음$/,
              ""
            );
            el.figureCaption.textContent = base
              ? base + " · 이미지 없음"
              : "이미지 없음";
            el.figureCaption.hidden = false;
          });
        }
        if (prevSrc !== imgSrc) {
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
      renderFigRefHints(sent);
      renderCiteRefHints(sent);
      void refreshSentenceKo(plainSentenceForTranslate(body));
      const sk = sttSentenceKey();
      if (sk !== sttBoundKey) {
        sttBoundKey = sk;
        resetSttPracticePanel();
      }
    } else if (uiPhase === "loading") {
      setSentenceDisplay(
        "논문을 읽고 있어요.\n잡음을 걸러 읽기 좋게\n다듬는 중이에요.",
        true
      );
      renderFigRefHints(null);
      renderCiteRefHints(null);
      clearSentenceKo();
      sttBoundKey = null;
      resetSttPracticePanel();
    } else if (state.figures.length > 0) {
      setSentenceDisplay(
        "문장 없음\n스캔본이거나 텍스트 추출에\n실패했을 수 있어요.",
        true
      );
      renderFigRefHints(null);
      renderCiteRefHints(null);
      clearSentenceKo();
      sttBoundKey = null;
      resetSttPracticePanel();
    } else {
      setSentenceDisplay(
        "문장이 없습니다.\n파일을 열어 주세요.",
        true
      );
      renderFigRefHints(null);
      renderCiteRefHints(null);
      clearSentenceKo();
      sttBoundKey = null;
      resetSttPracticePanel();
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

  let notesSyncTimer = 0;
  let notesSyncBusy = false;
  /** @type {boolean|null} null=미확인 */
  let gcsNotesAvailable = null;

  /** @type {{ enabled: boolean, clientId: string|null, providers: {google?:boolean,kakao?:boolean,email?:boolean}, user: object|null, dialogMode: string, cloudUrl: string|null, isAdmin: boolean }} */
  let authState = {
    enabled: false,
    clientId: null,
    providers: {},
    user: null,
    dialogMode: "login",
    cloudUrl: null,
    isAdmin: false,
  };

  function applyAccountScope(uid) {
    // design/79 — reload uid-scoped opt-in; logout clears via empty uid → OFF.
    loadShadowingPrefs();
    if (window.AsrShadowingPractice) AsrShadowingPractice.syncEntryBtn();
    void refreshShadowingServerFlag();

    if (AsrNotes && typeof AsrNotes.setAccountScope === "function") {
      AsrNotes.setAccountScope(uid || null);
    }
    if (
      typeof AsrProgress !== "undefined" &&
      AsrProgress &&
      AsrProgress.setAccountScope
    ) {
      AsrProgress.setAccountScope(uid || null);
    }
  }

  function setAuthDialogStatus(msg, kind) {
    if (!el.authDialogStatus) return;
    el.authDialogStatus.textContent = msg || "";
    el.authDialogStatus.classList.toggle("is-error", kind === "error");
  }

  function renderAuthChrome() {
    const enabled = !!authState.enabled;
    const user = authState.user;
    if (el.authLoginBtn) el.authLoginBtn.hidden = !enabled || !!user;
    if (el.authLogoutBtn) el.authLogoutBtn.hidden = !enabled || !user;
    if (el.authAccountBtn) el.authAccountBtn.hidden = !enabled || !user;
    // WHY: 사용량은 운영자만 — 일반 로그인 유저에게 버튼 숨김 (design/27)
    if (el.usageBtn) el.usageBtn.hidden = !enabled || !user || !authState.isAdmin;
    if (el.cloudUrlLink) {
      const cloud = authState.cloudUrl;
      const here = window.location.origin.replace(/\/$/, "");
      // WHY: 로컬 8770 일 때만 「클라우드」로 Run URL 안내 (이미 Run이면 숨김)
      const show =
        !!cloud && cloud.replace(/\/$/, "") !== here;
      el.cloudUrlLink.hidden = !show;
      if (show) {
        el.cloudUrlLink.href = cloud;
      }
    }
    if (el.authUserLabel) {
      if (enabled && user) {
        el.authUserLabel.hidden = false;
        el.authUserLabel.textContent = user.email || user.name || user.uid;
        el.authUserLabel.title = user.uid;
      } else {
        el.authUserLabel.hidden = true;
        el.authUserLabel.textContent = "";
      }
    }
  }

  function paintAuthDialog() {
    const p = authState.providers || {};
    const linking = authState.dialogMode === "link";
    const user = authState.user;
    if (el.authDialogTitle) {
      el.authDialogTitle.textContent = linking ? "계정 연결" : "계속하기";
    }
    if (el.authDialogHint) {
      el.authDialogHint.hidden = linking;
    }
    if (el.authProviderStack) {
      el.authProviderStack.hidden = linking;
    }
    if (el.authLinkPanel) el.authLinkPanel.hidden = !linking;
    if (el.authKakaoBtn) el.authKakaoBtn.hidden = linking || !p.kakao;
    if (el.authGoogleBtn) el.authGoogleBtn.hidden = linking || !p.google;
    if (el.authEmailToggleBtn) el.authEmailToggleBtn.hidden = linking || !p.email;
    if (el.authLinkKakaoBtn) el.authLinkKakaoBtn.hidden = !linking || !p.kakao;
    if (el.authLinkGoogleBtn) el.authLinkGoogleBtn.hidden = !linking || !p.google;
    // design/85 — email link-via-password removed; OAuth link only.
    if (el.authLinkEmailBtn) el.authLinkEmailBtn.hidden = true;
    if (el.authEmailPanel) {
      el.authEmailPanel.hidden = true;
    }
    if (el.googleSignInMount) {
      el.googleSignInMount.hidden = true;
      el.googleSignInMount.innerHTML = "";
    }
    if (linking && el.authLinkList && user) {
      const linked = Array.isArray(user.providers) ? user.providers : [];
      el.authLinkList.innerHTML = "";
      ["google", "kakao", "email"].forEach(function (name) {
        const li = document.createElement("li");
        const label =
          name === "google" ? "Google" : name === "kakao" ? "카카오" : "이메일";
        const on = linked.indexOf(name) >= 0;
        li.innerHTML =
          "<span>" +
          label +
          (on ? " · 연결됨" : " · 없음") +
          "</span>";
        if (on && linked.length > 1) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "upload-btn upload-btn-ghost";
          btn.textContent = "해제";
          btn.addEventListener("click", function () {
            void unlinkProvider(name);
          });
          li.appendChild(btn);
        }
        el.authLinkList.appendChild(li);
      });
    }
  }

  function openAuthDialog(mode) {
    authState.dialogMode = mode === "link" ? "link" : "login";
    setAuthDialogStatus("");
    paintAuthDialog();
    if (el.authDialog && typeof el.authDialog.showModal === "function") {
      el.authDialog.showModal();
    }
  }

  async function afterAuthSuccess(data, msg) {
    authState.user = data.user || null;
    applyAccountScope(authState.user && authState.user.uid);
    try {
      const st = await fetch("/api/auth/status", { credentials: "same-origin" });
      const d = await st.json().catch(() => ({}));
      authState.isAdmin = !!d.is_admin;
      if (d.user) authState.user = d.user;
    } catch (_) {
      /* ignore */
    }
    renderAuthChrome();
    setUploadStatus(msg || "로그인됨", "");
    applyLoginGateChrome(false);
    if (el.authDialog && el.authDialog.open) el.authDialog.close();
    loadTranslatePrefs();
    loadSectionReviewPrefs();
    loadGuidePrefs();
    if (translatePrefs.enabled) render();
    // design/84 — after identity, invite waiting before reader boot
    await enterAppOrAccessWait();
  }

  async function completeGoogleCredential(credential, mode) {
    if (!credential) return;
    const res = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        credential,
        mode: mode === "link" ? "link" : "login",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.message || "Google 로그인에 실패했습니다.");
    }
    await afterAuthSuccess(
      data,
      mode === "link" ? "Google 연결됨" : "Google 로그인됨"
    );
  }

  function loadGis(mode) {
    if (!authState.clientId) {
      setAuthDialogStatus("Google 클라이언트 ID가 없습니다.", "error");
      return;
    }
    const start = () => {
      try {
        window.google.accounts.id.initialize({
          client_id: authState.clientId,
          callback: (resp) => {
            void completeGoogleCredential(
              resp && resp.credential,
              mode
            ).catch((err) => {
              setAuthDialogStatus(String(err.message || err), "error");
            });
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        // WHY: 「구글로 계속하기」+ 공식 버튼 이중 노출 방지 — 계정 선택 먼저, 실패 시 공식 버튼만
        const customBtn =
          mode === "link" ? el.authLinkGoogleBtn : el.authGoogleBtn;
        if (customBtn) customBtn.hidden = true;
        if (el.authEmailPanel) el.authEmailPanel.hidden = true;
        setAuthDialogStatus("Google 계정 선택 창을 여는 중…", "");

        let showedFallback = false;
        const showOfficialButton = () => {
          if (showedFallback || !el.googleSignInMount) return;
          showedFallback = true;
          el.googleSignInMount.hidden = false;
          el.googleSignInMount.innerHTML = "";
          window.google.accounts.id.renderButton(el.googleSignInMount, {
            theme: "outline",
            size: "large",
            text: mode === "link" ? "continue_with" : "signin_with",
            shape: "rectangular",
            width: 280,
          });
          setAuthDialogStatus("아래 Google 버튼으로 계속하세요.", "");
        };

        window.google.accounts.id.prompt((notification) => {
          try {
            if (!notification) {
              showOfficialButton();
              return;
            }
            const needButton =
              (notification.isNotDisplayed && notification.isNotDisplayed()) ||
              (notification.isSkippedMoment && notification.isSkippedMoment()) ||
              (notification.isDismissedMoment &&
                notification.isDismissedMoment());
            if (needButton) showOfficialButton();
            else setAuthDialogStatus("");
          } catch (_) {
            showOfficialButton();
          }
        });
      } catch (err) {
        setAuthDialogStatus(String(err.message || err), "error");
      }
    };
    if (window.google && window.google.accounts && window.google.accounts.id) {
      start();
      return;
    }
    const existing = document.querySelector('script[data-asr-gis="1"]');
    if (existing) {
      existing.addEventListener("load", start, { once: true });
      return;
    }
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.dataset.asrGis = "1";
    s.onload = start;
    s.onerror = () =>
      setAuthDialogStatus("Google 스크립트를 불러오지 못했습니다.", "error");
    document.head.appendChild(s);
  }

  /** design/85 — web email login is magic-link only (no password UI). */
  async function requestEmailMagicLink() {
    const email = el.authEmailInput ? el.authEmailInput.value.trim() : "";
    if (!email) {
      throw new Error("이메일을 입력하세요.");
    }
    // WHY: omit client → server builds browser open URL (cookie + /?auth=).
    const res = await fetch("/api/auth/email/magic/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ email, client: "web" }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      // FAIL-CLOSED: never claim the link was sent on error.
      throw new Error(data.message || "로그인 링크를 보내지 못했습니다.");
    }
    setAuthDialogStatus(
      data.message || "로그인 링크를 이메일로 보냈습니다. 메일함에서 열어 주세요.",
      ""
    );
  }

  async function unlinkProvider(provider) {
    const res = await fetch("/api/auth/unlink", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ provider }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      setAuthDialogStatus(data.message || "해제 실패", "error");
      return;
    }
    authState.user = data.user || null;
    paintAuthDialog();
    renderAuthChrome();
    setAuthDialogStatus("연결 해제됨", "");
  }

  async function initAuth() {
    try {
      const res = await fetch("/api/auth/status", { credentials: "same-origin" });
      const data = await res.json().catch(() => ({}));
      authState.enabled = !!data.auth_enabled;
      authState.clientId = data.client_id || null;
      authState.providers = data.providers || {};
      authState.user = data.user || null;
      authState.cloudUrl = data.cloud_url || null;
      authState.isAdmin = !!data.is_admin;
      applyAccountScope(authState.user && authState.user.uid);
      renderAuthChrome();
      loadTranslatePrefs();
      loadSectionReviewPrefs();
      loadGuidePrefs();
      const params = new URLSearchParams(window.location.search);
      if (params.get("auth_error")) {
        setUploadStatus("로그인 실패: " + params.get("auth_error"), "error");
      } else if (params.get("auth") === "logged_in" || params.get("auth") === "linked") {
        setUploadStatus(
          params.get("auth") === "linked" ? "계정 연결됨" : "로그인됨",
          ""
        );
        history.replaceState({}, "", window.location.pathname);
        await pullNotesFromCloud();
      }
    } catch (_) {
      authState = {
        enabled: false,
        clientId: null,
        providers: {},
        user: null,
        dialogMode: "login",
        cloudUrl: null,
        isAdmin: false,
      };
      renderAuthChrome();
      loadTranslatePrefs();
      loadSectionReviewPrefs();
      loadGuidePrefs();
    }
  }

  async function openUsageDialog() {
    if (!el.usageDialog || !authState.user || !authState.isAdmin) return;
    if (el.usageDialogBody) el.usageDialogBody.textContent = "불러오는 중…";
    if (typeof el.usageDialog.showModal === "function") {
      el.usageDialog.showModal();
    }
    try {
      const meRes = await fetch("/api/usage", { credentials: "same-origin" });
      const me = await meRes.json().catch(() => ({}));
      let text = "";
      if (!meRes.ok || me.ok === false) {
        text = me.error || "사용량을 불러오지 못했습니다.";
      } else {
        const t = me.totals || {};
        const e = me.estimate_usd || {};
        text =
          "나 · 추정 $" +
          (e.total_usd != null ? e.total_usd : "?") +
          "\n" +
          "Gemini 호출 " +
          (t.gemini_calls || 0) +
          " · in/out 문자 " +
          (t.gemini_input_chars || 0) +
          "/" +
          (t.gemini_output_chars || 0) +
          "\n" +
          "TTS 클라우드 " +
          (t.tts_cloud_calls || 0) +
          "회 · " +
          (t.tts_chars || 0) +
          "자\n" +
          "GCS up/down " +
          (t.gcs_upload_bytes || 0) +
          "/" +
          (t.gcs_download_bytes || 0) +
          " B\n" +
          (me.estimate_note || "");
      }
      if (authState.isAdmin) {
        const adRes = await fetch("/api/usage/admin", {
          credentials: "same-origin",
        });
        const ad = await adRes.json().catch(() => ({}));
        if (adRes.ok && ad.ok !== false) {
          const g = ad.grand_estimate_usd || {};
          text +=
            "\n\n—— 관리자 전체 ——\n추정 합 $" +
            (g.total_usd != null ? g.total_usd : "?") +
            " · 유저 " +
            ((ad.users && ad.users.length) || 0) +
            "명";
          (ad.users || []).slice(0, 40).forEach(function (u) {
            const ue = (u.estimate_usd && u.estimate_usd.total_usd) || 0;
            text +=
              "\n· " +
              (u.email || u.uid) +
              " · $" +
              ue;
          });
        }
      }
      if (el.usageDialogBody) el.usageDialogBody.textContent = text;
      if (el.usageDialogNote && me.estimate_note) {
        el.usageDialogNote.textContent = me.estimate_note;
      }
    } catch (err) {
      if (el.usageDialogBody) {
        el.usageDialogBody.textContent =
          (err && err.message) || "사용량 오류";
      }
    }
  }

  async function logoutAuth() {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
    } catch (_) {
      /* ignore */
    }
    authState.user = null;
    applyAccountScope(null);
    // design/133 — shared browser: discard prior user's papers/tabs/reader.
    // WHY: applyAccountScope clears notes/progress keys but left papers[] in memory.
    try {
      if (typeof stopTts === "function") stopTts();
    } catch (_) {
      /* ignore */
    }
    ingestCancelRequested = false;
    ingestActiveJobId = null;
    papers = [];
    activePaperIndex = 0;
    state.figures = [];
    state.sentences = [];
    state.figureIndex = 0;
    state.sentenceIndex = 0;
    state.title = "";
    state.sessionId = null;
    state.translateDigests = {};
    state.references = [];
    state.translatePending = false;
    uiPhase = "boot";
    if (el.stageBadge) el.stageBadge.textContent = "";
    setSentenceDisplay("", true);
    renderPaperTabs();
    updateCacheDeleteBtn();
    renderAuthChrome();
    loadTranslatePrefs();
    loadSectionReviewPrefs();
    loadGuidePrefs();
    if (translatePrefs.enabled) render();
    else clearSentenceKo();
    setUploadStatus("로그아웃됨", "");
    stopAccessPoll();
    applyAccessWaitingChrome(false);
    loginGateUnlocked = false;
    // design/83 — logout returns to login-only shell when gate on.
    if (loginRequiredFlag && authState.enabled) {
      applyLoginGateChrome(true);
      openAuthDialog("login");
    }
  }

  function writeNotesStore(store) {
    if (!AsrNotes) return;
    AsrNotes.writeRaw(store);
    scheduleNotesCloudPush();
  }

  function scheduleNotesCloudPush() {
    if (notesSyncTimer) window.clearTimeout(notesSyncTimer);
    notesSyncTimer = window.setTimeout(function () {
      notesSyncTimer = 0;
      pushNotesToCloud();
    }, 1600);
  }

  async function pullNotesFromCloud() {
    if (!AsrNotes || notesSyncBusy) return;
    notesSyncBusy = true;
    try {
      const res = await fetch("/api/notes/sync", { credentials: "same-origin" });
      if (!res.ok) return;
      const data = await res.json();
      gcsNotesAvailable = !!data.available;
      if (!data.available || !data.store) return;
      const local = AsrNotes.readRaw();
      const merged = AsrNotes.mergeStores
        ? AsrNotes.mergeStores(local, data.store)
        : data.store;
      AsrNotes.writeRaw(merged);
      const put = await fetch("/api/notes/sync", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store: merged }),
      });
      if (!put.ok) return;
      const putData = await put.json();
      if (putData && putData.available && putData.store) {
        AsrNotes.writeRaw(putData.store);
      }
    } catch (_) {
      /* offline */
    } finally {
      notesSyncBusy = false;
    }
  }

  async function pushNotesToCloud() {
    if (!AsrNotes) return;
    if (gcsNotesAvailable === false) return;
    if (notesSyncBusy) return;
    notesSyncBusy = true;
    try {
      const store = AsrNotes.readRaw();
      const res = await fetch("/api/notes/sync", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store: store }),
      });
      if (!res.ok) return;
      const data = await res.json();
      gcsNotesAvailable = !!data.available;
      if (data.available && data.store) {
        AsrNotes.writeRaw(data.store);
      }
    } catch (_) {
      /* offline */
    } finally {
      notesSyncBusy = false;
    }
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
  function stopVoicePlayback(opts) {
    opts = opts || {};
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
    // WHY: design/52 — 이어 재생 큐는 keepSequence 일 때만 유지 (클립 전환)
    if (!opts.keepSequence) {
      hideSectionReviewClipActions();
      noteUi.voiceSeq = null;
    }
  }

  /** design/54 — 일시 정지 시 보이는 클립 액션 숨김 */
  function hideSectionReviewClipActions() {
    var seq = noteUi.voiceSeq;
    if (seq && seq.actionsEl) {
      seq.actionsEl.hidden = true;
    }
    if (seq && seq.statusEl && !noteUi.reviewRecordSid) {
      seq.statusEl.textContent = "";
    }
  }

  /**
   * design/54 — 현재 클립(i) 기준 다시 듣기·재녹음·끝내기 표시.
   * sentence_index 불변.
   */
  function showSectionReviewClipActions() {
    var seq = noteUi.voiceSeq;
    if (!seq || !seq.actionsEl) return;
    var i = seq.i | 0;
    var entry = seq.entries && seq.entries[i];
    if (!entry || !entry.sid) {
      seq.actionsEl.hidden = true;
      return;
    }
    seq.actionsEl.hidden = false;
    if (seq.statusEl) {
      seq.statusEl.textContent =
        "문장 " + (i + 1) + "/" + seq.queue.length + " · 다시 듣거나 녹음";
    }
  }

  /**
   * IndexedDB blobKey → 최신 한 건만 재생 (이전 재생은 끊음).
   * IDB miss 시 GCS(/api/voice/blobs)에서 받아 IDB에 채움.
   * @param {string} blobKey
   * @param {{ onStatus?: function(string), onMissing?: function(), onEnded?: function(), keepSequence?: boolean }} opts
   * @returns {Promise<boolean>}
   */
  async function playVoiceBlobKey(blobKey, opts) {
    opts = opts || {};
    if (!blobKey || !window.AsrVoiceIdb) {
      if (opts.onMissing) opts.onMissing();
      return false;
    }
    stopVoicePlayback({ keepSequence: !!opts.keepSequence });
    stopTtsEngineOnly();
    try {
      var blob = await window.AsrVoiceIdb.getBlob(blobKey);
      if (!blob || !(blob.size > 0)) {
        blob = await fetchVoiceBlobFromCloud(blobKey);
        if (!blob || !(blob.size > 0)) {
          if (opts.onMissing) opts.onMissing();
          return false;
        }
      }
      var url = URL.createObjectURL(blob);
      noteUi.voiceObjectUrl = url;
      var a = new Audio(url);
      noteUi.voiceAudio = a;
      noteUi.voicePlayingKey = blobKey;
      a.onended = function () {
        // 클립만 정리 — 시퀀스는 onEnded 가 이어 감
        if (noteUi.voiceAudio === a) {
          noteUi.voiceAudio = null;
        }
        if (noteUi.voiceObjectUrl === url) {
          try {
            URL.revokeObjectURL(url);
          } catch (_) {
            /* ignore */
          }
          noteUi.voiceObjectUrl = null;
        }
        noteUi.voicePlayingKey = null;
        if (opts.onEnded) {
          opts.onEnded();
        } else {
          if (!opts.keepSequence) noteUi.voiceSeq = null;
          if (opts.onStatus) opts.onStatus("");
        }
      };
      a.onerror = function () {
        // WHY: 시퀀스 중이면 클립만 끊고 onEnded 로 다음 — 한 클립 실패로 전체 중단하지 않음
        stopVoicePlayback({ keepSequence: !!opts.keepSequence });
        if (opts.onStatus) opts.onStatus("재생 실패");
        if (opts.keepSequence && opts.onEnded) {
          opts.onEnded();
        }
      };
      await a.play();
      if (opts.onStatus) opts.onStatus("재생 중…");
      return true;
    } catch (_) {
      stopVoicePlayback({ keepSequence: !!opts.keepSequence });
      if (opts.onStatus) opts.onStatus("재생 실패");
      return false;
    }
  }

  /**
   * GCS → IDB 캐시. 실패·미설정 시 null.
   * @param {string} blobKey
   * @returns {Promise<Blob|null>}
   */
  async function fetchVoiceBlobFromCloud(blobKey) {
    if (!blobKey || !window.AsrVoiceIdb) return null;
    try {
      var res = await fetch(
        "/api/voice/blobs?key=" + encodeURIComponent(blobKey)
      );
      if (!res.ok) return null;
      var buf = await res.arrayBuffer();
      if (!buf || !buf.byteLength) return null;
      var ctype = res.headers.get("content-type") || "audio/webm";
      var blob = new Blob([buf], { type: ctype });
      try {
        await window.AsrVoiceIdb.putBlob(blobKey, blob);
      } catch (_) {
        /* IDB 실패해도 재생은 가능 */
      }
      return blob;
    } catch (_) {
      return null;
    }
  }

  /**
   * 로컬 녹음 → GCS best-effort (노트 메타 push 와 별개).
   * @param {string} blobKey
   * @param {Blob} blob
   */
  async function uploadVoiceBlobToCloud(blobKey, blob) {
    if (!blobKey || !blob || !(blob.size > 0)) return;
    try {
      var res = await fetch(
        "/api/voice/blobs?key=" + encodeURIComponent(blobKey),
        {
          method: "PUT",
          headers: {
            "Content-Type": blob.type || "application/octet-stream",
          },
          body: blob,
        }
      );
      if (!res.ok) return;
      var data = await res.json();
      if (data && data.available === false) {
        /* 버킷 없음 — 무시 */
      }
    } catch (_) {
      /* offline */
    }
  }

  /**
   * 문장 단위 목소리 녹음 (노트 오버레이 · 되새김질 클립 재녹음 공용).
   * append-only · sentence_index 불변.
   * @param {string} sentenceId
   * @param {{ onStatus?: function(string), onSaved?: function({rev:number, blobKey:string, mime:string}), toggleStop?: boolean }} opts
   */
  async function recordVoiceForSentence(sentenceId, opts) {
    opts = opts || {};
    var sid = String(sentenceId || "").trim();
    if (!sid) {
      if (opts.onStatus) opts.onStatus("문장 없음");
      return;
    }
    // 토글 중지: 같은 sid 녹음 중이면 stop
    if (noteUi.recording && (opts.toggleStop !== false)) {
      if (noteUi.reviewRecordSid === sid || noteUi.boundSentenceId === sid) {
        try {
          if (noteUi.mediaRecorder && noteUi.mediaRecorder.state !== "inactive") {
            noteUi.mediaRecorder.stop();
          }
        } catch (_) {
          /* ignore */
        }
        return;
      }
      // 다른 문장 녹음 중이면 먼저 끊고 진행
      try {
        if (noteUi.mediaRecorder && noteUi.mediaRecorder.state !== "inactive") {
          noteUi.mediaRecorder.stop();
        }
      } catch (_) {
        /* ignore */
      }
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (opts.onStatus) opts.onStatus("이 브라우저는 녹음을 지원하지 않습니다.");
      else setNoteVoiceStatus("이 브라우저는 녹음을 지원하지 않습니다.");
      return;
    }
    // 재생 중이면 녹음 전에 멈춤 (시퀀스 포커스는 유지할 수 있게 pause 만)
    if (noteUi.voiceAudio && !noteUi.voiceAudio.paused) {
      try {
        noteUi.voiceAudio.pause();
      } catch (_) {
        /* ignore */
      }
      if (noteUi.voiceSeq) noteUi.voiceSeq.paused = true;
    }
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      var chunks = [];
      noteUi.recordChunks = chunks;
      var rec = new MediaRecorder(stream);
      noteUi.mediaRecorder = rec;
      noteUi.recording = true;
      noteUi.reviewRecordSid = sid;
      if (el.noteVoiceBtn && noteUi.open && noteUi.boundSentenceId === sid) {
        el.noteVoiceBtn.textContent = "녹음 중지";
      }
      if (opts.onStatus) opts.onStatus("녹음 중…");
      else setNoteVoiceStatus("녹음 중…");
      rec.ondataavailable = function (ev) {
        if (ev.data && ev.data.size) chunks.push(ev.data);
      };
      rec.onstop = async function () {
        noteUi.recording = false;
        noteUi.reviewRecordSid = null;
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
          if (opts.onStatus) opts.onStatus("녹음 실패");
          else setNoteVoiceStatus("녹음 실패");
          return;
        }
        var pk = currentPaperKey();
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
          uploadVoiceBlobToCloud(blobKey, blob);
          var msg = "저장됨 · rev " + result.rev;
          if (opts.onStatus) opts.onStatus(msg);
          else setNoteVoiceStatus(msg);
          if (noteUi.open && noteUi.boundSentenceId === sid) {
            updateNoteVoiceButtons(pk, sid);
          }
          if (opts.onSaved) {
            opts.onSaved({
              rev: result.rev,
              blobKey: blobKey,
              mime: blob.type || "audio/webm",
            });
          }
        } catch (err) {
          if (opts.onStatus) opts.onStatus("저장 실패");
          else setNoteVoiceStatus("저장 실패");
        }
      };
      rec.start();
    } catch (err) {
      noteUi.recording = false;
      noteUi.reviewRecordSid = null;
      if (opts.onStatus) opts.onStatus("마이크 권한이 필요합니다.");
      else setNoteVoiceStatus("마이크 권한이 필요합니다.");
    }
  }

  async function toggleNoteVoiceRecord() {
    if (!noteUi.boundSentenceId) return;
    await recordVoiceForSentence(noteUi.boundSentenceId, { toggleStop: true });
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

  /** design/56 — flow 인라인 편집 textarea 포커스 여부 */
  function isFocusInSectionReviewEdit() {
    return !!(
      noteUi.flowEdit &&
      noteUi.flowEdit.ta &&
      document.activeElement === noteUi.flowEdit.ta
    );
  }

  /** @returns {HTMLElement[]} */
  function getSectionReviewFlowSegs() {
    if (!el.sectionReviewList) return [];
    return Array.prototype.slice.call(
      el.sectionReviewList.querySelectorAll(".section-review-flow-seg")
    );
  }

  /**
   * design/56 — 세그먼트 포커스 (sentence_index 불변).
   * @param {number} index
   */
  function focusSectionReviewSeg(index) {
    var segs = getSectionReviewFlowSegs();
    if (!segs.length) {
      noteUi.flowSegIndex = 0;
      if (el.sectionReviewContinue) {
        try {
          el.sectionReviewContinue.focus();
        } catch (_) {
          /* ignore */
        }
      } else if (el.sectionReviewSheet) {
        try {
          el.sectionReviewSheet.focus();
        } catch (_) {
          /* ignore */
        }
      }
      return;
    }
    var i = index | 0;
    if (i < 0) i = 0;
    if (i >= segs.length) i = segs.length - 1;
    noteUi.flowSegIndex = i;
    segs.forEach(function (s, j) {
      s.classList.toggle("is-flow-focus", j === i);
    });
    try {
      segs[i].focus();
    } catch (_) {
      /* ignore */
    }
  }

  /**
   * design/56 — 되새김질 전용 키. 처리하면 true (문서 핸들러가 return).
   * 문장 박스 ←/→ · Enter · Esc 감각에 맞춤 · 인덱스는 건드리지 않음.
   * @param {KeyboardEvent} ev
   * @returns {boolean}
   */
  function handleSectionReviewKeys(ev) {
    if (!isSectionReviewOpen()) return false;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return false;

    // 편집 중(textarea): Esc=취소만 · 화살표는 캐럿 이동(문서 핸들러가 TEXTAREA 에서 return)
    if (isFocusInSectionReviewEdit()) {
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        cancelSectionReviewFlowEdit();
        focusSectionReviewSeg(noteUi.flowSegIndex | 0);
        return true;
      }
      return false;
    }
    if (noteUi.flowEdit && ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      cancelSectionReviewFlowEdit();
      focusSectionReviewSeg(noteUi.flowSegIndex | 0);
      return true;
    }

    var tag = (ev.target && ev.target.tagName) || "";
    // 목소리/계속 읽기 버튼 위에서는 Space/Enter 네이티브 클릭 유지
    if (
      tag === "BUTTON" &&
      (ev.key === " " || ev.key === "Enter") &&
      ev.target &&
      ev.target.closest &&
      ev.target.closest(".section-review-sheet")
    ) {
      return false;
    }

    if (ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      closeSectionReview();
      return true;
    }

    var segs = getSectionReviewFlowSegs();

    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      ev.preventDefault();
      ev.stopPropagation();
      if (!segs.length) {
        focusSectionReviewSeg(0);
        return true;
      }
      var cur = noteUi.flowSegIndex | 0;
      // activeElement 가 세그먼트면 그 인덱스 우선
      var ae = document.activeElement;
      for (var si = 0; si < segs.length; si++) {
        if (segs[si] === ae) {
          cur = si;
          break;
        }
      }
      var next = cur + (ev.key === "ArrowRight" ? 1 : -1);
      if (next < 0) next = 0;
      if (next >= segs.length) next = segs.length - 1;
      focusSectionReviewSeg(next);
      return true;
    }

    // Shift+←/→ · ↑/↓ 도 읽기 인덱스 변경 방지
    if (
      ev.key === "ArrowUp" ||
      ev.key === "ArrowDown" ||
      ((ev.key === "ArrowLeft" || ev.key === "ArrowRight") && ev.shiftKey)
    ) {
      ev.preventDefault();
      return true;
    }

    if (
      (ev.key === "Enter" || ev.key === " " || ev.code === "Space") &&
      !ev.isComposing &&
      !ev.shiftKey
    ) {
      // 세그먼트 있으면 포커스된 것 편집 · 없으면 계속 읽기
      if (segs.length) {
        ev.preventDefault();
        ev.stopPropagation();
        var ix = noteUi.flowSegIndex | 0;
        var ae2 = document.activeElement;
        for (var j = 0; j < segs.length; j++) {
          if (segs[j] === ae2) {
            ix = j;
            break;
          }
        }
        focusSectionReviewSeg(ix);
        var seg = segs[ix];
        if (seg) {
          // click 핸들러와 동일 경로
          seg.click();
        }
        return true;
      }
      if (ev.key === "Enter" && el.sectionReviewContinue) {
        ev.preventDefault();
        ev.stopPropagation();
        el.sectionReviewContinue.click();
        return true;
      }
    }

    // Tab: 논문 전환 대신 세그먼트·계속 읽기 순환
    if (ev.key === "Tab") {
      ev.preventDefault();
      ev.stopPropagation();
      if (!segs.length) {
        if (el.sectionReviewContinue) {
          try {
            el.sectionReviewContinue.focus();
          } catch (_) {
            /* ignore */
          }
        }
        return true;
      }
      var tcur = noteUi.flowSegIndex | 0;
      var tnext = tcur + (ev.shiftKey ? -1 : 1);
      if (tnext < 0) {
        if (el.sectionReviewContinue) {
          noteUi.flowSegIndex = 0;
          try {
            el.sectionReviewContinue.focus();
          } catch (_) {
            /* ignore */
          }
          return true;
        }
        tnext = segs.length - 1;
      }
      if (tnext >= segs.length) {
        if (el.sectionReviewContinue) {
          try {
            el.sectionReviewContinue.focus();
          } catch (_) {
            /* ignore */
          }
          return true;
        }
        tnext = 0;
      }
      focusSectionReviewSeg(tnext);
      return true;
    }

    // 문장/그림/전체화면/숫자 탭 등 읽기 단축키 차단 (인덱스 불변)
    if (
      ev.key === "f" ||
      ev.key === "F" ||
      (ev.key >= "1" && ev.key <= "9") ||
      (ev.code && /^Digit[1-9]$/.test(ev.code)) ||
      (ev.code && /^Numpad[1-9]$/.test(ev.code))
    ) {
      ev.preventDefault();
      return true;
    }

    return false;
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

  function sectionReviewStorageKey() {
    const uid = authState.user && authState.user.uid;
    return uid
      ? SECTION_REVIEW_STORAGE_BASE + "." + String(uid)
      : SECTION_REVIEW_STORAGE_BASE;
  }

  function loadSectionReviewPrefs() {
    // WHY: design/53 — 손상·빈 값·이상 타입은 기본 켜짐으로 복구 (읽기 UX 유지)
    try {
      const raw = localStorage.getItem(sectionReviewStorageKey());
      if (!raw) {
        sectionReviewPrefs.enabled = true;
      } else {
        const data = JSON.parse(raw);
        if (data && typeof data === "object" && "enabled" in data) {
          sectionReviewPrefs.enabled = !!data.enabled;
        } else if (typeof data === "boolean") {
          sectionReviewPrefs.enabled = data;
        } else {
          sectionReviewPrefs.enabled = true;
        }
      }
    } catch (_) {
      sectionReviewPrefs.enabled = true;
    }
    syncSectionReviewBtn();
  }

  function saveSectionReviewPrefs() {
    try {
      localStorage.setItem(
        sectionReviewStorageKey(),
        JSON.stringify({ enabled: !!sectionReviewPrefs.enabled })
      );
    } catch (_) {
      /* ignore quota / private mode */
    }
  }

  function syncSectionReviewBtn() {
    if (!el.sectionReviewBtn) return;
    el.sectionReviewBtn.setAttribute(
      "aria-pressed",
      sectionReviewPrefs.enabled ? "true" : "false"
    );
    el.sectionReviewBtn.title = sectionReviewPrefs.enabled
      ? "되새김질 켜짐 — 섹션이 바뀔 때 리뷰 (클릭하면 끔)"
      : "되새김질 꺼짐 — 섹션 경계에서도 리뷰 없음 (클릭하면 켬)";
  }

  // ——— design/59 Guide placement ———
  function guideStorageKey() {
    const uid = authState.user && authState.user.uid;
    return uid ? GUIDE_STORAGE_BASE + "." + String(uid) : GUIDE_STORAGE_BASE;
  }



  let shadowingChunksCacheId = null;

  function setShadowingChunksBanner(message, { retry = false, cacheId = null } = {}) {
    if (!el.shadowingChunksBanner) return;
    shadowingChunksCacheId = cacheId;
    if (!message) {
      el.shadowingChunksBanner.hidden = true;
      if (el.shadowingChunksRetry) el.shadowingChunksRetry.hidden = true;
      return;
    }
    el.shadowingChunksBanner.hidden = false;
    if (el.shadowingChunksMsg) el.shadowingChunksMsg.textContent = message;
    if (el.shadowingChunksRetry) {
      el.shadowingChunksRetry.hidden = !retry;
    }
  }

  async function ensureShadowingChunks(cacheId) {
    // WHY: only when server kill + user opt-in (like translate on).
    if (!shadowingPrefs.serverAvailable || !shadowingPrefs.enabled) {
      setShadowingChunksBanner("");
      return;
    }
    if (!cacheId || !authState.user) {
      return;
    }
    try {
      const res = await fetch(
        "/api/shadowing/chunks/" + encodeURIComponent(cacheId),
        { credentials: "same-origin" }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setShadowingChunksBanner(
          (data && data.message) || "연습 구간을 확인하지 못했습니다.",
          { retry: true, cacheId }
        );
        return;
      }
      const plan = data.plan || {};
      if (plan.status === "ok") {
        setShadowingChunksBanner("");
        return;
      }
      // backfill / retry — design/119: pending must continue; never clear as done early
      setShadowingChunksBanner("연습 구간을 준비하는 중…", { retry: false, cacheId });
      var maxRounds = 40;
      var body = {};
      for (var round = 0; round < maxRounds; round++) {
        if (round > 0) {
          setShadowingChunksBanner(
            "연습 구간을 이어서 준비하는 중… (" + (round + 1) + "/" + maxRounds + ")",
            { retry: false, cacheId }
          );
        }
        const built = await fetch(
          "/api/shadowing/chunks/" + encodeURIComponent(cacheId) + "/build",
          {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ practice_enabled: true }),
          }
        );
        body = await built.json().catch(() => ({}));
        var st = body.plan && body.plan.status;
        // Fail-closed: only status=ok clears the banner (pending ≠ success).
        if (built.ok && body.ok && st === "ok") {
          setShadowingChunksBanner("");
          return;
        }
        if (built.ok && body.ok && body.continue && st === "pending") {
          continue;
        }
        setShadowingChunksBanner(
          (body && body.message) || "연습 구간을 만들지 못했습니다. 다시 시도해 주세요.",
          { retry: true, cacheId }
        );
        return;
      }
      setShadowingChunksBanner(
        (body && body.message) ||
          "연습 구간 준비가 끝나지 않았습니다. 다시 시도해 주세요.",
        { retry: true, cacheId }
      );
    } catch (_) {
      setShadowingChunksBanner("연습 구간 준비 중 오류가 났습니다. 다시 시도해 주세요.", {
        retry: true,
        cacheId,
      });
    }
  }

  function shadowingStorageKey() {
    const uid = authState.user && authState.user.uid;
    return uid
      ? SHADOWING_STORAGE_BASE + "." + String(uid)
      : SHADOWING_STORAGE_BASE;
  }

  function loadShadowingPrefs() {
    // WHY: product default OFF; garbage → false (fail-closed).
    shadowingPrefs.enabled = false;
    try {
      const raw = localStorage.getItem(shadowingStorageKey());
      if (raw) {
        const data = JSON.parse(raw);
        if (data && typeof data === "object" && "enabled" in data) {
          shadowingPrefs.enabled = !!data.enabled;
        } else if (typeof data === "boolean") {
          shadowingPrefs.enabled = data;
        }
      }
    } catch (_) {
      shadowingPrefs.enabled = false;
    }
    syncShadowingPracticeUi();
  }

  function saveShadowingPrefs() {
    try {
      localStorage.setItem(
        shadowingStorageKey(),
        JSON.stringify({ enabled: !!shadowingPrefs.enabled })
      );
    } catch (_) {
      /* ignore quota / private mode */
    }
  }

  function syncShadowingPracticeUi() {
    if (window.AsrShadowingPractice) AsrShadowingPractice.syncEntryBtn();
    if (!el.shadowingPracticeCheck) return;
    const avail = !!shadowingPrefs.serverAvailable;
    el.shadowingPracticeCheck.disabled =
      !avail || !(authState.user && authState.user.uid);
    // WHY: kill off → show unchecked even if stale local ON (no false success).
    el.shadowingPracticeCheck.checked = avail && !!shadowingPrefs.enabled;
    if (el.shadowingPracticeHint) {
      el.shadowingPracticeHint.textContent = avail
        ? "기본은 꺼짐입니다. 켜면 헤더 ⋯「연습」에서 따라 말하기를 씁니다 (로그인·청크 준비 필요)."
        : "서버에서 쉐도잉 연습이 꺼져 있습니다.";
    }
  }

  async function refreshShadowingServerFlag() {
    try {
      const res = await fetch("/api/status", { credentials: "same-origin" });
      const st = await res.json().catch(() => ({}));
      shadowingPrefs.serverAvailable = !!(
        st &&
        (st.shadowing_practice || st.mobile_shadowing_practice)
      );
    } catch (_) {
      shadowingPrefs.serverAvailable = false;
    }
    syncShadowingPracticeUi();
  }

  function loadGuidePrefs() {
    // EDGE: 손상 JSON · 비객체 → nestInMore=false · showPanelHints=false
    // WHY: design/60 — 예전 v1에 nestInMore만 있어도 showPanelHints는 기본 숨김
    try {
      const raw = localStorage.getItem(guideStorageKey());
      if (!raw) {
        guidePrefs.nestInMore = false;
        guidePrefs.showPanelHints = false;
      } else {
        const data = JSON.parse(raw);
        if (data && typeof data === "object") {
          if ("nestInMore" in data) {
            guidePrefs.nestInMore = !!data.nestInMore;
          } else {
            guidePrefs.nestInMore = false;
          }
          if ("showPanelHints" in data) {
            guidePrefs.showPanelHints = !!data.showPanelHints;
          } else {
            guidePrefs.showPanelHints = false;
          }
        } else if (typeof data === "boolean") {
          // 구형 boolean = nestInMore 만
          guidePrefs.nestInMore = data;
          guidePrefs.showPanelHints = false;
        } else {
          guidePrefs.nestInMore = false;
          guidePrefs.showPanelHints = false;
        }
      }
    } catch (_) {
      guidePrefs.nestInMore = false;
      guidePrefs.showPanelHints = false;
    }
    applyGuidePlacement();
    applyPanelHints();
  }

  function saveGuidePrefs() {
    try {
      localStorage.setItem(
        guideStorageKey(),
        JSON.stringify({
          nestInMore: !!guidePrefs.nestInMore,
          showPanelHints: !!guidePrefs.showPanelHints,
        })
      );
    } catch (_) {
      /* ignore quota / private mode */
    }
  }

  /**
   * Guide 버튼을 밖 슬롯 ↔ ⋯ 메뉴로 옮긴다.
   * EDGE: 슬롯/메뉴/버튼 누락 시 no-op (구 HTML 캐시).
   */
  function applyGuidePlacement() {
    if (!el.guideBtn) return;
    if (el.guideNestCheck) {
      el.guideNestCheck.checked = !!guidePrefs.nestInMore;
    }
    if (guidePrefs.nestInMore) {
      if (el.headerMoreMenu && el.guideBtn.parentElement !== el.headerMoreMenu) {
        el.headerMoreMenu.insertBefore(
          el.guideBtn,
          el.headerMoreMenu.firstChild
        );
      }
      el.guideBtn.setAttribute("role", "menuitem");
    } else if (el.guideOutsideSlot) {
      if (el.guideBtn.parentElement !== el.guideOutsideSlot) {
        el.guideOutsideSlot.appendChild(el.guideBtn);
      }
      el.guideBtn.removeAttribute("role");
    }
  }

  /**
   * design/60 — 문장·그림 패널 `.panel-chrome-hint` 표시.
   * 노트/되새김/veil hint 는 건드리지 않음 (읽기 크롬만).
   * EDGE: 노드 없으면 no-op · hidden 속성으로 기본 숨김.
   */
  function applyPanelHints() {
    var show = !!guidePrefs.showPanelHints;
    if (el.sentenceHint) el.sentenceHint.hidden = !show;
    if (el.figureHint) el.figureHint.hidden = !show;
    if (el.guideShowHintsCheck) {
      el.guideShowHintsCheck.checked = show;
    }
  }

  function isGuideOpen() {
    return !!(el.guideDialog && el.guideDialog.open);
  }

  function openGuideDialog() {
    void refreshShadowingServerFlag().then(function () {
      loadShadowingPrefs();
    });

    if (!el.guideDialog || typeof el.guideDialog.showModal !== "function") {
      return;
    }
    setHeaderMoreOpen(false);
    if (el.ttsDialog && el.ttsDialog.open) el.ttsDialog.close();
    if (el.libraryDialog && el.libraryDialog.open) el.libraryDialog.close();
    if (el.guideNestCheck) {
      el.guideNestCheck.checked = !!guidePrefs.nestInMore;
    }
    if (el.guideShowHintsCheck) {
      el.guideShowHintsCheck.checked = !!guidePrefs.showPanelHints;
    }
    el.guideDialog.showModal();
  }

  function closeGuideDialog() {
    if (el.guideDialog && el.guideDialog.open) el.guideDialog.close();
  }

  function openSectionReview(section) {
    // WHY: design/53 — prefs off 이면 호출되어도 no-op (인덱스·store 불변)
    if (!sectionReviewPrefs.enabled) return;
    if (!el.sectionReviewOverlay || !el.sectionReviewList || !AsrNotes) return;
    // 재오픈 시 이전 편집 핸들만 버림 (저장은 close/commit 경로)
    noteUi.flowEdit = null;
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
    var secKey = String(section || "body").trim().toLowerCase() || "body";
    var digest =
      (state.translateDigests && state.translateDigests[secKey]) ||
      (state.translateDigests && state.translateDigests[section]) ||
      null;
    var hasDigest =
      translatePrefs.enabled &&
      digest &&
      (String(digest.ko || "").trim() || String(digest.en || "").trim());
    // WHY: design/51+55+56+57 — 이어 보기 · 콕 수정 · 키보드 · 흰 십자
    if (el.sectionReviewHint) {
      el.sectionReviewHint.textContent = hasDigest
        ? "위쪽은 이 구간 번역 정리본입니다. 아래는 기록을 이어서 본 것입니다. ←/→ · Enter · Esc · 흰 십자로 위치를 봅니다 (문장 위치는 그대로)."
        : "아래는 이 구간 기록을 이어서 본 것입니다. ←/→ · Enter · Esc · 흰 십자로 위치를 봅니다 (문장 위치는 그대로).";
    }
    var ids = AsrNotes.sentenceIdsInSection(state.sentences, section);
    var pk = currentPaperKey();
    var store = readNotesStore();
    el.sectionReviewList.innerHTML = "";
    // WHY: design/40 — 섹션 digest를 되새김질 상단에 고정
    if (hasDigest) {
      var digLi = document.createElement("li");
      digLi.className = "section-review-digest";
      var digTitle = document.createElement("div");
      digTitle.className = "section-review-digest-label";
      digTitle.textContent = "번역 정리본";
      digLi.appendChild(digTitle);
      if (String(digest.ko || "").trim()) {
        var digKo = document.createElement("p");
        digKo.className = "section-review-digest-ko";
        digKo.textContent = String(digest.ko).trim();
        digLi.appendChild(digKo);
      }
      if (String(digest.en || "").trim()) {
        var digEn = document.createElement("p");
        digEn.className = "section-review-digest-en";
        digEn.textContent = String(digest.en).trim();
        digLi.appendChild(digEn);
      }
      el.sectionReviewList.appendChild(digLi);
    }
    if (!ids.length) {
      var empty = document.createElement("li");
      empty.className = "section-review-item-body is-empty";
      empty.textContent = "이 구간에 문장이 없습니다.";
      el.sectionReviewList.appendChild(empty);
      window.setTimeout(function () {
        focusSectionReviewSeg(0);
      }, 0);
      return;
    }

    // design/51+55 — 최신 노트를 등장 순 세그먼트로 이어 보기 · 클릭 시 그 문장만 수정
    var flowEntries = [];
    var voiceEntries = [];
    ids.forEach(function (sid) {
      var latest = AsrNotes.latestText(store, pk, sid);
      var trimmed = latest ? String(latest).trim() : "";
      if (trimmed) flowEntries.push({ sid: sid, text: trimmed });
      var voice = AsrNotes.latestVoice(store, pk, sid);
      if (voice && voice.blobKey) {
        voiceEntries.push({ sid: sid, voice: voice });
      }
    });
    var flowLi = document.createElement("li");
    flowLi.className = "section-review-flow-wrap";
    var flow = document.createElement("div");
    flow.className = "section-review-flow";
    flow.setAttribute("role", "article");
    flow.setAttribute("aria-label", "구간 기록 이어 보기");
    if (!flowEntries.length) {
      flow.className = "section-review-flow is-empty";
      flow.textContent = "이 구간에 아직 기록이 없습니다.";
    } else {
      flowEntries.forEach(function (entry) {
        var seg = document.createElement("div");
        seg.className = "section-review-flow-seg";
        seg.dataset.sentenceId = entry.sid;
        seg.tabIndex = 0;
        seg.setAttribute("role", "button");
        seg.setAttribute(
          "aria-label",
          "이 문장 기록 수정 (읽기 위치는 바꾸지 않음)"
        );
        seg.title = "클릭하여 이 문장 기록만 수정";
        var body = document.createElement("div");
        body.className = "section-review-flow-seg-body";
        body.textContent = entry.text;
        seg.appendChild(body);
        seg.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          beginSectionReviewFlowEdit(seg, entry, section, pk);
        });
        seg.addEventListener("keydown", function (ev) {
          if (ev.key !== "Enter" && ev.key !== " ") return;
          ev.preventDefault();
          ev.stopPropagation();
          beginSectionReviewFlowEdit(seg, entry, section, pk);
        });
        flow.appendChild(seg);
      });
    }
    flowLi.appendChild(flow);
    el.sectionReviewList.appendChild(flowLi);

    // WHY: design/52+54 — 이어 듣기 · 일시 정지 시 이 문장만 다시 듣기/재녹음
    if (voiceEntries.length) {
      var barLi = document.createElement("li");
      barLi.className = "section-review-voice-bar";
      var barLabel = document.createElement("span");
      barLabel.className = "section-review-voice-bar-label";
      barLabel.textContent = "목소리";
      barLi.appendChild(barLabel);
      var seqBtn = document.createElement("button");
      seqBtn.type = "button";
      seqBtn.className = "section-review-voice-btn section-review-voice-seq";
      seqBtn.title =
        "이 구간 목소리를 순서대로 이어 듣기 (" + voiceEntries.length + "개)";
      seqBtn.setAttribute("aria-label", "구간 목소리 이어 듣기");
      seqBtn.textContent = "▶ 이어 듣기";
      barLi.appendChild(seqBtn);
      var actionsEl = document.createElement("span");
      actionsEl.className = "section-review-clip-actions";
      actionsEl.hidden = true;
      var replayBtn = document.createElement("button");
      replayBtn.type = "button";
      replayBtn.className = "section-review-voice-btn section-review-clip-replay";
      replayBtn.textContent = "이 문장만 듣기";
      replayBtn.title = "일시 정지한 문장 목소리만 다시 듣기";
      var rerecordBtn = document.createElement("button");
      rerecordBtn.type = "button";
      rerecordBtn.className =
        "section-review-voice-btn section-review-clip-rerecord";
      rerecordBtn.textContent = "이 문장만 녹음";
      rerecordBtn.title = "일시 정지한 문장만 다시 녹음 (인덱스 불변)";
      var endBtn = document.createElement("button");
      endBtn.type = "button";
      endBtn.className = "section-review-voice-btn section-review-clip-end";
      endBtn.textContent = "끝내기";
      endBtn.title = "이어 듣기 종료";
      actionsEl.appendChild(replayBtn);
      actionsEl.appendChild(rerecordBtn);
      actionsEl.appendChild(endBtn);
      barLi.appendChild(actionsEl);
      var statusEl = document.createElement("span");
      statusEl.className = "section-review-clip-status";
      statusEl.setAttribute("aria-live", "polite");
      barLi.appendChild(statusEl);
      seqBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        onSectionReviewPlayVoiceSequence(voiceEntries, seqBtn, {
          actionsEl: actionsEl,
          statusEl: statusEl,
          replayBtn: replayBtn,
          rerecordBtn: rerecordBtn,
          endBtn: endBtn,
        });
      });
      replayBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        onSectionReviewClipReplay();
      });
      rerecordBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        onSectionReviewClipRerecord(rerecordBtn);
      });
      endBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        onSectionReviewClipEnd(seqBtn);
      });
      el.sectionReviewList.appendChild(barLi);
    }

    noteUi.flowSegIndex = 0;
    window.setTimeout(function () {
      focusSectionReviewSeg(0);
    }, 0);
  }

  /**
   * design/55 — flow 세그먼트 인라인 편집. sentence_index 불변.
   * @param {HTMLElement} seg
   * @param {{ sid: string, text: string }} entry
   * @param {string} section
   * @param {string} pk
   */
  function beginSectionReviewFlowEdit(seg, entry, section, pk) {
    if (!seg || !entry || !entry.sid) return;
    pk = pk || currentPaperKey();
    // 다른 세그먼트 편집 중이면 저장 후 DOM 갱신 → 다시 이 세그먼트 편집
    if (noteUi.flowEdit && noteUi.flowEdit.sid !== entry.sid) {
      var prevSec = noteUi.flowEdit.section || section;
      commitSectionReviewFlowEdit({ reopen: false });
      openSectionReview(prevSec);
      var sidSafe = String(entry.sid).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      var nextSeg =
        el.sectionReviewList &&
        el.sectionReviewList.querySelector(
          '.section-review-flow-seg[data-sentence-id="' + sidSafe + '"]'
        );
      if (!nextSeg) return;
      var latest = AsrNotes
        ? AsrNotes.latestText(readNotesStore(), pk, entry.sid)
        : entry.text;
      beginSectionReviewFlowEdit(
        nextSeg,
        { sid: entry.sid, text: latest || "" },
        section,
        pk
      );
      return;
    }
    if (noteUi.flowEdit && noteUi.flowEdit.sid === entry.sid) return;

    seg.classList.add("is-editing");
    seg.innerHTML = "";
    var ta = document.createElement("textarea");
    ta.className = "section-review-flow-edit";
    ta.value = entry.text || "";
    ta.setAttribute("aria-label", "이 문장 기록 편집");
    ta.rows = Math.min(
      12,
      Math.max(3, String(entry.text || "").split("\n").length + 1)
    );
    var actions = document.createElement("div");
    actions.className = "section-review-flow-edit-actions";
    var saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "upload-btn";
    saveBtn.textContent = "저장";
    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "upload-btn upload-btn-ghost";
    cancelBtn.textContent = "취소";
    var status = document.createElement("span");
    status.className = "section-review-flow-edit-status";
    status.setAttribute("aria-live", "polite");
    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    actions.appendChild(status);
    seg.appendChild(ta);
    seg.appendChild(actions);
    noteUi.flowEdit = {
      sid: String(entry.sid),
      ta: ta,
      section: section,
      pk: pk,
      statusEl: status,
    };
    saveBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      commitSectionReviewFlowEdit({ reopen: true });
    });
    cancelBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      cancelSectionReviewFlowEdit();
    });
    ta.addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    window.setTimeout(function () {
      try {
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
      } catch (_) {
        /* ignore */
      }
    }, 0);
  }

  /**
   * @param {{ reopen?: boolean }} opts
   */
  function commitSectionReviewFlowEdit(opts) {
    opts = opts || {};
    var edit = noteUi.flowEdit;
    if (!edit || !edit.sid || !edit.ta) {
      noteUi.flowEdit = null;
      return;
    }
    var sid = edit.sid;
    var section = edit.section;
    var pk = edit.pk || currentPaperKey();
    var text = edit.ta.value;
    noteUi.flowEdit = null;
    // WHY: append-only · 동일 본문이면 no-op (notes_revisions)
    try {
      commitNoteRevision(pk, sid, text);
    } catch (_) {
      /* ignore */
    }
    // 노트 오버레이가 같은 문장이면 draft 동기화
    if (noteUi.open && noteUi.boundSentenceId === sid && el.noteTextarea) {
      el.noteTextarea.value = String(text || "").replace(/\s+$/g, "");
      noteUi.draft = el.noteTextarea.value;
    }
    if (opts.reopen !== false && isSectionReviewOpen() && section) {
      openSectionReview(section);
    }
  }

  function cancelSectionReviewFlowEdit() {
    var edit = noteUi.flowEdit;
    var section = edit && edit.section;
    noteUi.flowEdit = null;
    if (isSectionReviewOpen() && section) {
      openSectionReview(section);
    }
  }

  /**
   * design/52+54 — 구간 최신 목소리를 등장 순으로 이어 재생.
   * 재생 중 클릭 = 일시 정지 + 이 문장 액션. 정지 중 클릭 = 계속.
   * sentence_index 불변. 없는 blob 은 건너뜀.
   * @param {{ sid: string, voice: { blobKey: string, rev?: number } }[]} entries
   * @param {HTMLButtonElement} playBtn
   * @param {{ actionsEl?: HTMLElement, statusEl?: HTMLElement, replayBtn?: HTMLElement, rerecordBtn?: HTMLElement, endBtn?: HTMLElement }} ui
   */
  async function onSectionReviewPlayVoiceSequence(entries, playBtn, ui) {
    ui = ui || {};
    var list = [];
    (entries || []).forEach(function (e) {
      var k = e && e.voice && e.voice.blobKey;
      if (k && e.sid) list.push({ sid: String(e.sid), voice: e.voice });
    });
    if (!list.length) return;
    var queue = list.map(function (e) {
      return String(e.voice.blobKey);
    });

    // 재생 중 → 일시 정지 (design/54) · 클립 액션 표시
    if (
      noteUi.voiceSeq &&
      noteUi.voiceAudio &&
      !noteUi.voiceAudio.paused &&
      !noteUi.voiceSeq.paused
    ) {
      try {
        noteUi.voiceAudio.pause();
      } catch (_) {
        /* ignore */
      }
      noteUi.voiceSeq.paused = true;
      noteUi.voiceSeq.clipFinished = false;
      showSectionReviewClipActions();
      if (playBtn) {
        playBtn.disabled = false;
        var pi = noteUi.voiceSeq.i | 0;
        playBtn.textContent =
          "▶ 계속 (" + (pi + 1) + "/" + noteUi.voiceSeq.queue.length + ")";
      }
      return;
    }

    // 일시 정지 중 · 오디오 살아 있음 → 같은 위치에서 재개
    if (
      noteUi.voiceSeq &&
      noteUi.voiceSeq.paused &&
      noteUi.voiceAudio &&
      noteUi.voicePlayingKey
    ) {
      noteUi.voiceSeq.paused = false;
      noteUi.voiceSeq.clipFinished = false;
      hideSectionReviewClipActions();
      try {
        await noteUi.voiceAudio.play();
        if (playBtn) {
          var ri = noteUi.voiceSeq.i | 0;
          playBtn.textContent =
            "⏸ 일시정지 (" + (ri + 1) + "/" + noteUi.voiceSeq.queue.length + ")";
        }
      } catch (_) {
        if (playBtn) playBtn.textContent = "실패";
      }
      return;
    }

    // 일시 정지 중 · 오디오 없음 (클립만 듣기 끝·재녹음 후) → 현재/다음부터 시퀀스 재개
    if (noteUi.voiceSeq && noteUi.voiceSeq.paused && noteUi.voiceSeq.gen) {
      var seqResume = noteUi.voiceSeq;
      var resumeGen = seqResume.gen;
      var resumeBtn = playBtn || seqResume.btn;
      var startAt = seqResume.i | 0;
      if (seqResume.clipFinished) startAt = startAt + 1;
      seqResume.paused = false;
      seqResume.clipFinished = false;
      hideSectionReviewClipActions();

      async function resumePlayAt(i) {
        if (!noteUi.voiceSeq || noteUi.voiceSeq.gen !== resumeGen) return;
        if (i >= seqResume.queue.length) {
          stopVoicePlayback();
          if (resumeBtn) {
            resumeBtn.disabled = false;
            resumeBtn.textContent = "▶ 이어 듣기";
          }
          return;
        }
        noteUi.voiceSeq.i = i;
        noteUi.voiceSeq.paused = false;
        if (resumeBtn) {
          resumeBtn.disabled = false;
          resumeBtn.textContent =
            "⏸ 일시정지 (" + (i + 1) + "/" + seqResume.queue.length + ")";
        }
        function advance() {
          if (!noteUi.voiceSeq || noteUi.voiceSeq.gen !== resumeGen) return;
          if (noteUi.voiceSeq.i !== i) return;
          if (noteUi.voiceSeq.paused) return;
          resumePlayAt(i + 1);
        }
        var key = seqResume.queue[i];
        var ok = await playVoiceBlobKey(key, {
          keepSequence: true,
          onEnded: advance,
          onStatus: function (msg) {
            if (!resumeBtn) return;
            if (msg === "재생 실패") resumeBtn.textContent = "실패";
          },
        });
        if (!ok) advance();
      }

      if (resumeBtn) {
        resumeBtn.disabled = true;
        resumeBtn.textContent = "…";
      }
      await resumePlayAt(startAt);
      return;
    }

    // 전환 중(오디오 없음)·잔여 시퀀스 → 취소 후 새로 시작
    if (noteUi.voiceSeq && !noteUi.voiceAudio && !noteUi.voiceSeq.paused) {
      stopVoicePlayback();
      if (playBtn) {
        playBtn.disabled = false;
        playBtn.textContent = "▶ 이어 듣기";
      }
    }

    noteUi.voiceSeqGen += 1;
    var gen = noteUi.voiceSeqGen;
    noteUi.voiceSeq = {
      queue: queue,
      entries: list,
      i: 0,
      gen: gen,
      btn: playBtn || null,
      paused: false,
      clipFinished: false,
      actionsEl: ui.actionsEl || null,
      statusEl: ui.statusEl || null,
    };

    function labelPause(i) {
      return "⏸ 일시정지 (" + (i + 1) + "/" + queue.length + ")";
    }

    async function playAt(i) {
      if (!noteUi.voiceSeq || noteUi.voiceSeq.gen !== gen) return;
      if (i >= queue.length) {
        stopVoicePlayback();
        if (playBtn) {
          playBtn.disabled = false;
          playBtn.textContent = "▶ 이어 듣기";
        }
        return;
      }
      noteUi.voiceSeq.i = i;
      noteUi.voiceSeq.paused = false;
      hideSectionReviewClipActions();
      if (playBtn) {
        playBtn.disabled = false;
        playBtn.textContent = labelPause(i);
      }
      function advance() {
        if (!noteUi.voiceSeq || noteUi.voiceSeq.gen !== gen) return;
        if (noteUi.voiceSeq.i !== i) return;
        if (noteUi.voiceSeq.paused) return;
        playAt(i + 1);
      }
      var ok = await playVoiceBlobKey(queue[i], {
        keepSequence: true,
        onEnded: advance,
        onStatus: function (msg) {
          if (!playBtn) return;
          if (msg === "재생 실패") playBtn.textContent = "실패";
        },
      });
      if (!ok) advance();
    }

    if (playBtn) {
      playBtn.disabled = true;
      playBtn.textContent = "…";
    }
    await playAt(0);
  }

  /** design/54 — 일시 정지된 현재 클립만 다시 재생 (시퀀스 유지·일시 정지 상태) */
  async function onSectionReviewClipReplay() {
    var seq = noteUi.voiceSeq;
    if (!seq || !seq.entries) return;
    var i = seq.i | 0;
    var entry = seq.entries[i];
    var key =
      (entry && entry.voice && entry.voice.blobKey) ||
      (seq.queue && seq.queue[i]) ||
      "";
    if (!key) {
      if (seq.statusEl) seq.statusEl.textContent = "목소리 없음";
      return;
    }
    seq.paused = true;
    seq.clipFinished = false;
    if (seq.btn) {
      seq.btn.textContent =
        "▶ 계속 (" + (i + 1) + "/" + seq.queue.length + ")";
    }
    await playVoiceBlobKey(String(key), {
      keepSequence: true,
      onEnded: function () {
        // 클립만 끝 — 시퀀스는 일시 정지 유지 (자동 다음 안 함)
        if (noteUi.voiceSeq && noteUi.voiceSeq.gen === seq.gen) {
          noteUi.voiceSeq.paused = true;
          noteUi.voiceSeq.clipFinished = true;
          showSectionReviewClipActions();
        }
      },
      onStatus: function (msg) {
        if (seq.statusEl && msg === "재생 실패") {
          seq.statusEl.textContent = "재생 실패";
        }
      },
    });
  }

  /** design/54 — 현재 클립 문장만 재녹음 (인덱스 불변) */
  async function onSectionReviewClipRerecord(rerecordBtn) {
    var seq = noteUi.voiceSeq;
    if (!seq || !seq.entries) return;
    var i = seq.i | 0;
    var entry = seq.entries[i];
    if (!entry || !entry.sid) {
      if (seq.statusEl) seq.statusEl.textContent = "문장 없음";
      return;
    }
    // 녹음 중이면 토글로 중지
    if (noteUi.recording && noteUi.reviewRecordSid === entry.sid) {
      await recordVoiceForSentence(entry.sid, {
        toggleStop: true,
        onStatus: function (msg) {
          if (seq.statusEl) seq.statusEl.textContent = msg;
          if (rerecordBtn && msg === "녹음 중…") {
            rerecordBtn.textContent = "녹음 중지";
          } else if (rerecordBtn) {
            rerecordBtn.textContent = "이 문장만 녹음";
          }
        },
      });
      return;
    }
    if (rerecordBtn) rerecordBtn.textContent = "녹음 중지";
    await recordVoiceForSentence(entry.sid, {
      toggleStop: true,
      onStatus: function (msg) {
        if (seq.statusEl) seq.statusEl.textContent = msg;
        if (rerecordBtn) {
          rerecordBtn.textContent =
            msg === "녹음 중…" ? "녹음 중지" : "이 문장만 녹음";
        }
      },
      onSaved: function (saved) {
        // 큐·엔트리의 현재 클립을 최신 blob 으로 교체
        if (!noteUi.voiceSeq || noteUi.voiceSeq.gen !== seq.gen) return;
        var cur = noteUi.voiceSeq.entries[i];
        if (cur) {
          cur.voice = {
            blobKey: saved.blobKey,
            rev: saved.rev,
            mime: saved.mime,
          };
        }
        noteUi.voiceSeq.queue[i] = saved.blobKey;
        noteUi.voiceSeq.paused = true;
        noteUi.voiceSeq.clipFinished = false;
        showSectionReviewClipActions();
        if (noteUi.voiceSeq.statusEl) {
          noteUi.voiceSeq.statusEl.textContent =
            "저장됨 · 이 문장만 듣기로 확인 가능";
        }
      },
    });
  }

  /** design/54 — 이어 듣기 완전 종료 */
  function onSectionReviewClipEnd(playBtn) {
    if (noteUi.recording) {
      try {
        if (noteUi.mediaRecorder && noteUi.mediaRecorder.state !== "inactive") {
          noteUi.mediaRecorder.stop();
        }
      } catch (_) {
        /* ignore */
      }
    }
    stopVoicePlayback();
    if (playBtn) {
      playBtn.disabled = false;
      playBtn.textContent = "▶ 이어 듣기";
    }
  }

  /** @deprecated design/52 — 단일 클립 대신 이어 듣기 사용. 테스트·호환용 유지. */
  async function onSectionReviewPlayVoice(sentenceId, blobKey, playBtn) {
    if (!blobKey) return;
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
    // WHY: design/55 — 시트 닫을 때 편집 중이면 저장
    if (noteUi.flowEdit) {
      commitSectionReviewFlowEdit({ reopen: false });
    }
    // WHY: design/54 — 시트 닫을 때 재녹음도 정리
    if (noteUi.recording && noteUi.reviewRecordSid) {
      try {
        if (noteUi.mediaRecorder && noteUi.mediaRecorder.state !== "inactive") {
          noteUi.mediaRecorder.stop();
        }
      } catch (_) {
        /* ignore */
      }
    }
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
    persistReadingProgress();
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
    ingestCancelRequested = false;
    ingestActiveJobId = null;
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
      const ingestUrl =
        shadowingPrefs.serverAvailable && shadowingPrefs.enabled
          ? "/api/ingest?shadowing_practice=1"
          : "/api/ingest";
      const res = await fetch(ingestUrl, { method: "POST", body });
      const start = await res.json().catch(() => ({}));
      if (!res.ok || start.ok === false) {
        throw new Error(start.message || `업로드 실패 (${res.status})`);
      }
      const jobId = start.job_id;
      if (!jobId) {
        throw new Error("작업 ID를 받지 못했어요.");
      }
      ingestActiveJobId = jobId;

      let data = null;
      let openedEarly = false;
      for (;;) {
        if (ingestCancelRequested) {
          throw new Error("__ASR_INGEST_CANCELLED__");
        }
        await new Promise((r) => setTimeout(r, 400));
        if (ingestCancelRequested) {
          throw new Error("__ASR_INGEST_CANCELLED__");
        }
        const stRes = await fetch(`/api/ingest/jobs/${encodeURIComponent(jobId)}`);
        const st = await stRes.json().catch(() => ({}));
        if (!stRes.ok && stRes.status === 404) {
          if (ingestCancelRequested) {
            throw new Error("__ASR_INGEST_CANCELLED__");
          }
          throw new Error(st.message || "작업을 찾을 수 없어요.");
        }
        const pct = typeof st.percent === "number" ? st.percent : 0;
        setUploadStatus(`읽는 중… ${pct}% · ${name}`, "busy");
        if (st.message) {
          el.stageBadge.textContent = `${st.message} · ${name}`;
        }
        // WHY: design/45 — 번역 전이라도 session_id 있으면 먼저 열기
        if (
          !openedEarly &&
          st.session_id &&
          Array.isArray(st.sentences) &&
          st.sentences.length
        ) {
          applySession(st, "ready", { asNewTab: true });
          openedEarly = true;
          setLoading(false);
          setUploadStatus(
            st.translate_pending
              ? `읽는 중 · 번역 진행… ${pct}% · ${name}`
              : `읽는 중… ${pct}% · ${name}`,
            "busy"
          );
        } else if (openedEarly && st.session_id && Array.isArray(st.sentences)) {
          // 데이터만 병합 — 보고 있는 문장 KO 스냅샷은 refreshSentenceKo 가 유지
          mergeTranslateProgress(st);
        }
        if (st.done) {
          if (st.ok === false && !st.session_id) {
            throw new Error(st.message || "처리에 실패했어요.");
          }
          data = st;
          break;
        }
      }

      if (openedEarly) {
        mergeTranslateProgress(data);
        state.translatePending = false;
        const paper = papers[activePaperIndex];
        if (paper) paper.translatePending = false;
        frozenKoSentenceId = null;
        frozenKoText = null;
        render();
      } else {
        applySession(data, "ready", { asNewTab: true });
      }
      const nS = state.sentences.length;
      const nF = state.figures.length;
      if (data.cache_id) {
        void ensureShadowingChunks(String(data.cache_id));
        const sc = data.shadowing_chunks;
        if (
          sc &&
          sc.status &&
          sc.status !== "ok" &&
          sc.status !== "skipped"
        ) {
          setShadowingChunksBanner(
            "연습 구간을 만들지 못했습니다. 다시 시도해 주세요.",
            { retry: true, cacheId: String(data.cache_id) }
          );
        }
      }
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
      if (String(err && err.message) === "__ASR_INGEST_CANCELLED__") {
        // design/132 — discard; no fake success session from cancel.
        setUploadStatus("업로드를 취소했습니다.", "");
        if (!papers.length) {
          uiPhase = "empty";
          el.stageBadge.textContent = "";
          setSentenceDisplay("", true);
        }
      } else {
        if (!papers.length) {
          uiPhase = "error";
          el.stageBadge.textContent = "ingest failed";
          setSentenceDisplay(String(err.message || err), true);
        }
        setUploadStatus(String(err.message || err), "error");
      }
    } finally {
      ingestCancelRequested = false;
      ingestActiveJobId = null;
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

  /* ---------- 그림 전체화면: 드래그 크롭 확대 · 확대 중 팬 ---------- */
  let cropDrag = null;
  /** @type {{ pointerId: number, lastX: number, lastY: number, moved: boolean, dist: number } | null} */
  let cropPan = null;
  let suppressFigureClick = false;

  function localPoint(ev) {
    const rect = el.figureViewport.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  }

  function endCropPan(ev) {
    if (!cropPan || (ev && ev.pointerId !== cropPan.pointerId)) return;
    const pan = cropPan;
    cropPan = null;
    if (el.figureViewport) el.figureViewport.classList.remove("is-panning");
    try {
      if (el.figureViewport && el.figureViewport.releasePointerCapture) {
        el.figureViewport.releasePointerCapture(pan.pointerId);
      }
    } catch (_) {
      /* ignore */
    }
    if (pan.moved) {
      suppressFigureClick = true;
      snapshotActivePaper();
      window.setTimeout(() => {
        suppressFigureClick = false;
      }, 0);
    }
  }

  el.figureViewport.addEventListener("pointerdown", (ev) => {
    if (!layout.fullscreen) return;
    if (ev.button != null && ev.button !== 0) return;
    ev.preventDefault();
    if (cropZoom.active) {
      // 확대 중: 드래그=팬(2×), 클릭(거의 안 움직임)=축소
      cropPan = {
        pointerId: ev.pointerId,
        lastX: ev.clientX,
        lastY: ev.clientY,
        moved: false,
        dist: 0,
      };
      el.figureViewport.classList.add("is-panning");
      try {
        el.figureViewport.setPointerCapture(ev.pointerId);
      } catch (_) {
        /* ignore */
      }
      return;
    }
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
    if (cropPan && ev.pointerId === cropPan.pointerId) {
      const dx = ev.clientX - cropPan.lastX;
      const dy = ev.clientY - cropPan.lastY;
      cropPan.lastX = ev.clientX;
      cropPan.lastY = ev.clientY;
      cropPan.dist += Math.hypot(dx, dy);
      if (cropPan.dist > 6) cropPan.moved = true;
      if (dx !== 0 || dy !== 0) panCropBy(dx, dy);
      return;
    }
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
    if (cropPan) {
      endCropPan(ev);
      return;
    }
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
      // WHY: design/56 — 편집 중 Esc 는 시트 닫기보다 취소 우선
      if (isSectionReviewOpen() && (isFocusInSectionReviewEdit() || noteUi.flowEdit)) {
        ev.preventDefault();
        ev.stopPropagation();
        cancelSectionReviewFlowEdit();
        focusSectionReviewSeg(noteUi.flowSegIndex | 0);
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

    // WHY: design/56 — 되새김질 키를 문장 박스 감각에 맞춤 (인덱스 불변)
    if (handleSectionReviewKeys(ev)) return;

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
      if (el.libraryDialog && el.libraryDialog.open) return;
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
  loadTranslatePrefs();
  loadSectionReviewPrefs();
  loadGuidePrefs();

  if (el.translateBtn) {
    el.translateBtn.addEventListener("click", () => {
      translatePrefs.enabled = !translatePrefs.enabled;
      saveTranslatePrefs();
      syncTranslateBtn();
      if (translatePrefs.enabled) render();
      else clearSentenceKo();
    });
  }

  // WHY: design/53 — 헤더「되새김」토글 · 끄면 열린 시트도 닫음
  if (el.sectionReviewBtn) {
    el.sectionReviewBtn.addEventListener("click", () => {
      sectionReviewPrefs.enabled = !sectionReviewPrefs.enabled;
      saveSectionReviewPrefs();
      syncSectionReviewBtn();
      if (!sectionReviewPrefs.enabled && isSectionReviewOpen()) {
        closeSectionReview({ resume: false });
      }
    });
  }

  // WHY: design/59 — Guide 열기 · ⋯ 안 넣기 체크
  if (el.guideBtn) {
    el.guideBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      openGuideDialog();
    });
  }
  if (el.guideDialogClose) {
    el.guideDialogClose.addEventListener("click", () => {
      closeGuideDialog();
    });
  }
  if (el.guideNestCheck) {
    el.guideNestCheck.addEventListener("change", () => {
      guidePrefs.nestInMore = !!el.guideNestCheck.checked;
      saveGuidePrefs();
      applyGuidePlacement();
    });
  }
  if (el.guideShowHintsCheck) {
    el.guideShowHintsCheck.addEventListener("change", () => {
      // WHY: design/60 — 화면 단축키 줄 on/off (인덱스·단축키 동작 불변)
      guidePrefs.showPanelHints = !!el.guideShowHintsCheck.checked;
      saveGuidePrefs();
      applyPanelHints();
    });
  }

  if (el.shadowingChunksRetry) {
    el.shadowingChunksRetry.addEventListener("click", function () {
      if (shadowingChunksCacheId) {
        void ensureShadowingChunks(shadowingChunksCacheId);
      }
    });
  }

  // design/82 — shadowing practice mode (separate dialog; gated).
  if (window.AsrShadowingPractice && typeof AsrShadowingPractice.configure === "function") {
    AsrShadowingPractice.configure({
      els: {
        practiceBtn: el.shadowingPracticeBtn,
        dialog: el.shadowingPracticeDialog,
        closeBtn: el.shadowingPracticeClose,
        meta: el.shadowingPracticeMeta,
        prompt: el.shadowingPracticePrompt,
        status: el.shadowingPracticeStatus,
        nextBtn: el.shadowingPracticeNext,
        skipBtn: el.shadowingPracticeSkip,
        retryBtn: el.shadowingPracticeRetry,
        replayBtn: el.shadowingPracticeReplay,
        continueBtn: el.shadowingPracticeContinue,
      },
      serverAvailable: function () {
        return !!shadowingPrefs.serverAvailable;
      },
      practiceEnabled: function () {
        return !!shadowingPrefs.enabled;
      },
      isLoggedIn: function () {
        return !!(authState.user && authState.user.uid);
      },
      cacheId: function () {
        return state.cacheId ? String(state.cacheId) : null;
      },
      readerSnapshot: function () {
        var sents = state.sentences || [];
        var idx = state.sentenceIndex || 0;
        var sent = sents[idx] || null;
        var ids = sents.map(function (s, i) {
          return String((s && (s.id || s.sentence_id)) || i);
        });
        var plain = "";
        if (sent) {
          plain = String(sent.text || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        }
        return {
          sentenceIndex: idx,
          sentenceCount: sents.length,
          sentenceId: String((sent && (sent.id || sent.sentence_id)) || idx),
          plainText: plain,
          sentenceIds: ids,
        };
      },
      goToSentence: function (i) {
        var n = (state.sentences || []).length;
        if (!n) return;
        state.sentenceIndex = Math.max(0, Math.min(n - 1, i | 0));
        renderSentence();
      },
    });
    AsrShadowingPractice.boot();
  }

  if (el.shadowingPracticeCheck) {
    el.shadowingPracticeCheck.addEventListener("change", function () {
      if (!shadowingPrefs.serverAvailable) {
        el.shadowingPracticeCheck.checked = false;
        syncShadowingPracticeUi();
        return;
      }
      shadowingPrefs.enabled = !!el.shadowingPracticeCheck.checked;
      saveShadowingPrefs();
    });
  }

  // WHY: design/37–38 — 서버 녹음 기본 · 브라우저 Web Speech 폴백 · 노트 voice 와 분리
  function initSttPractice() {
    if (sttPractice) return Promise.resolve();
    if (sttInitPromise) return sttInitPromise;
    sttInitPromise = (async () => {
      let mode = "browser";
      try {
        const res = await fetch("/api/status", { credentials: "same-origin" });
        const st = await res.json().catch(() => ({}));
        if (st && st.stt_server) mode = "server";
      } catch (_) {
        /* keep browser */
      }
      try {
        const raw = localStorage.getItem(
          authState.user && authState.user.uid
            ? "asr.stt.v1." + String(authState.user.uid)
            : "asr.stt.v1"
        );
        if (raw) {
          const data = JSON.parse(raw);
          if (data.mode === "browser" || data.mode === "server") {
            mode = data.mode;
          }
        }
      } catch (_) {
        /* ignore */
      }
      if (
        window.AsrSttPractice &&
        typeof window.AsrSttPractice.create === "function"
      ) {
        sttPractice = window.AsrSttPractice.create({
          mode: mode,
          getExpectedPlain: sttExpectedPlain,
          onUpdate: onSttPracticeUpdate,
        });
      }
    })();
    return sttInitPromise;
  }
  void initSttPractice();
  if (el.sttPracticeBtn) {
    el.sttPracticeBtn.addEventListener("click", () => {
      if (!state.sentences.length) {
        if (el.sttPracticePanel) el.sttPracticePanel.hidden = false;
        if (el.sttStatus) {
          el.sttStatus.textContent = "먼저 논문 문장을 열어 주세요.";
        }
        return;
      }
      void initSttPractice().then(() => {
        if (!sttPractice) {
          onSttPracticeUpdate({
            error: "unsupported",
            message:
              "이 브라우저는 음성 인식을 지원하지 않습니다 (Chrome 권장).",
          });
          return;
        }
        sttPractice.toggle();
      });
    });
  }

  el.uploadBtn.addEventListener("click", () => el.pdfInput.click());
  if (el.uploadCancelBtn) {
    el.uploadCancelBtn.addEventListener("click", () => {
      void requestIngestCancel();
    });
  }

  // WHY: design/58 — 헤더에는 「파일 열기」만 두고 도구는 ⋯ overflow.
  // 버튼 id·기존 리스너는 유지(DOM 이동만). Live Enable/IPS는 ASR 밖.
  // EDGE: 노드 없음(구 HTML)·이중 클릭 버블·노트/되새김 Esc와 충돌 방지.
  function isHeaderMoreOpen() {
    return !!(el.headerMoreMenu && !el.headerMoreMenu.hidden);
  }

  function setHeaderMoreOpen(on) {
    // null-safe: 정적 마크업 누락·부분 로드에서도 throw 금지
    if (!el.headerMoreMenu || !el.headerMoreBtn) return;
    var open = !!on;
    el.headerMoreMenu.hidden = !open;
    el.headerMoreBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function toggleHeaderMore() {
    setHeaderMoreOpen(!isHeaderMoreOpen());
  }

  if (el.headerMoreBtn) {
    el.headerMoreBtn.addEventListener("click", (ev) => {
      // stopPropagation: 바로 아래 document click이 같은 탭에서 즉시 닫지 않게
      ev.preventDefault();
      ev.stopPropagation();
      toggleHeaderMore();
    });
  }
  if (el.headerMoreMenu) {
    el.headerMoreMenu.addEventListener("click", (ev) => {
      // 메뉴 항목 클릭 후 닫기 — setTimeout(0): 토글 핸들러(aria-pressed)가 먼저 돌게
      var t = ev.target;
      if (!t) return;
      if (t === el.headerMoreMenu) return;
      var item = t.closest ? t.closest("button, a") : null;
      if (item && el.headerMoreMenu.contains(item)) {
        window.setTimeout(function () {
          setHeaderMoreOpen(false);
        }, 0);
      }
    });
  }
  document.addEventListener("click", (ev) => {
    if (!isHeaderMoreOpen()) return;
    var t = ev.target;
    // 메뉴·⋯ 버튼 내부 클릭은 유지
    if (el.headerMore && t && el.headerMore.contains(t)) return;
    setHeaderMoreOpen(false);
  });
  // Esc: 노트/되새김이 열려 있으면 그들 핸들러에 맡김 (메뉴만 열려 있을 때만 닫기)
  document.addEventListener(
    "keydown",
    (ev) => {
      if (ev.key !== "Escape") return;
      if (!isHeaderMoreOpen()) return;
      if (isNoteOpen() || isSectionReviewOpen() || isGuideOpen()) return;
      ev.preventDefault();
      setHeaderMoreOpen(false);
    },
    true
  );

  function setLibraryStatus(msg, kind) {
    if (!el.libraryStatus) return;
    el.libraryStatus.textContent = msg || "";
    el.libraryStatus.classList.toggle("is-error", kind === "error");
    el.libraryStatus.classList.toggle("is-busy", kind === "busy");
  }

  async function refreshLibraryList() {
    if (!el.libraryList) return;
    setLibraryStatus("목록 불러오는 중…", "busy");
    el.libraryList.innerHTML = "";
    try {
      const res = await fetch("/api/cache/papers");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setLibraryStatus(data.message || "목록을 불러오지 못했습니다.", "error");
        return;
      }
      const papersList = Array.isArray(data.papers) ? data.papers : [];
      if (!papersList.length) {
        setLibraryStatus("보관된 논문이 없습니다. 파일을 열어 분석하면 여기에 쌓입니다.", "");
        return;
      }
      setLibraryStatus(`${papersList.length}편`, "");
      papersList.forEach(function (item) {
        if (!item || !item.id) return;
        const li = document.createElement("li");
        li.className = "library-item";

        const row = document.createElement("div");
        row.className = "library-item-row";

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "library-item-btn";
        btn.dataset.cacheId = String(item.id);
        const title = document.createElement("span");
        title.className = "library-item-title";
        title.textContent = item.title || item.id;
        const meta = document.createElement("span");
        meta.className = "library-item-meta";
        const src = item.source === "docx" ? "Word" : "PDF";
        meta.textContent =
          src +
          " · 문장 " +
          (item.sentence_count || 0) +
          " · 그림 " +
          (item.figure_count || 0) +
          (item.has_source ? " · 원본" : "") +
          (item.stale ? " · 갱신 필요" : "");
        if (item.stale) {
          btn.classList.add("is-stale");
          meta.title = item.has_source
            ? "분석 파이프라인이 바뀌었습니다. 「재분석」으로 보관된 원본을 다시 돌릴 수 있습니다."
            : "분석 파이프라인이 바뀌었습니다. 열 수는 있고, 파일을 다시 열면 같은 보관 id로 재분석됩니다.";
        }
        btn.appendChild(title);
        btn.appendChild(meta);
        btn.addEventListener("click", function () {
          openCachedPaper(String(item.id), item.title || "", !!item.stale);
        });

        let reBtn = null;
        if (item.has_source) {
          reBtn = document.createElement("button");
          reBtn.type = "button";
          reBtn.className = "library-item-reanalyze";
          reBtn.title = "보관된 원본으로 다시 분석";
          reBtn.setAttribute("aria-label", "재분석");
          reBtn.textContent = "재분석";
          reBtn.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            reanalyzeLibraryPaper(String(item.id), item.title || "");
          });
        }

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "library-item-delete";
        delBtn.title = "보관본 삭제";
        delBtn.setAttribute("aria-label", "보관본 삭제");
        delBtn.textContent = "삭제";
        delBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          deleteLibraryPaper(String(item.id), item.title || "");
        });

        row.appendChild(btn);
        if (reBtn) row.appendChild(reBtn);
        row.appendChild(delBtn);
        li.appendChild(row);
        el.libraryList.appendChild(li);
      });
    } catch (err) {
      setLibraryStatus(String(err.message || err), "error");
    }
  }

  async function openLibraryDialog() {
    if (!el.libraryDialog || typeof el.libraryDialog.showModal !== "function") {
      return;
    }
    if (el.ttsDialog && el.ttsDialog.open) el.ttsDialog.close();
    el.libraryDialog.showModal();
    await refreshLibraryList();
  }

  /**
   * 보관본 즉시 열기 — GCS miss 시 서버가 pull (design/17·18).
   * stale 이어도 열어 노트 키 유지 · 상태만 경고 (design/19).
   * @param {string} cacheId
   * @param {string} titleHint
   * @param {boolean} [staleHint]
   */
  async function openCachedPaper(cacheId, titleHint, staleHint) {
    // design/121 — server pulls owner GCS first; clients must not treat errors as open.
    if (!cacheId) return;
    setLibraryStatus("여는 중…", "busy");
    setUploadStatus("보관본 여는 중…", "busy");
    setLoading(true);
    try {
      const res = await fetch(
        "/api/cache/papers/" + encodeURIComponent(cacheId) + "/open",
        { method: "POST" }
      );
      const data = await res.json().catch(() => ({}));
      // Fail-closed: HTTP error or explicit ok:false → never applySession.
      if (!res.ok || data.ok === false) {
        throw new Error(
          data.message || "보관본을 열 수 없습니다."
        );
      }
      const nSent = Array.isArray(data.sentences) ? data.sentences.length : 0;
      // design/114+121 — refuse title-only / empty sentence payloads.
      if (nSent < 1) {
        throw new Error(
          data.message ||
            "보관본에 문장이 없습니다. 재분석하거나 PDF를 다시 올려 주세요."
        );
      }
      applySession(data, "ready", { asNewTab: true });
      void prefetchFigureWindow();
      void ensureShadowingChunks(String(cacheId));
      const nS = state.sentences.length;
      const nF = state.figures.length;
      const stale = !!(data.stale || staleHint);
      if (stale) {
        const hint = data.has_source
          ? "보관에서 「재분석」"
          : "파일 다시 열면 재분석";
        setUploadStatus(
          `보관본(갱신 필요) · 문장 ${nS} · 그림 ${nF} · ${hint}`,
          "error"
        );
      } else {
        setUploadStatus(`보관본 · 문장 ${nS} · 그림 ${nF}`, "");
      }
      if (el.libraryDialog && el.libraryDialog.open) el.libraryDialog.close();
      setLibraryStatus("");
    } catch (err) {
      setLibraryStatus(String(err.message || err), "error");
      setUploadStatus(String(err.message || err), "error");
      void titleHint;
    } finally {
      setLoading(false);
    }
  }

  /**
   * 보관 원본으로 재분석 — job 폴링은 ingest 와 동일 (design/20).
   * @param {string} cacheId
   * @param {string} titleHint
   */
  async function reanalyzeLibraryPaper(cacheId, titleHint) {
    if (!cacheId) return;
    const label = shortTitle(titleHint || cacheId, 40);
    const ok = window.confirm(
      `「${label}」을 보관된 원본으로 다시 분석할까요?\n문장·그림이 갱신되고 보관 id는 유지됩니다.`
    );
    if (!ok) return;
    setLibraryStatus("재분석 중…", "busy");
    setUploadStatus("재분석 중… 0%", "busy");
    setLoading(true);
    if (el.libraryDialog && el.libraryDialog.open) el.libraryDialog.close();
    try {
      const res = await fetch(
        "/api/cache/papers/" + encodeURIComponent(cacheId) + "/reanalyze",
        { method: "POST" }
      );
      const start = await res.json().catch(() => ({}));
      if (!res.ok || start.ok === false) {
        throw new Error(start.message || "재분석을 시작하지 못했습니다.");
      }
      const jobId = start.job_id;
      if (!jobId) throw new Error("작업 ID를 받지 못했어요.");

      let data = null;
      for (;;) {
        await new Promise((r) => setTimeout(r, 400));
        const stRes = await fetch(
          "/api/ingest/jobs/" + encodeURIComponent(jobId)
        );
        const st = await stRes.json().catch(() => ({}));
        if (!stRes.ok && stRes.status === 404) {
          throw new Error(st.message || "작업을 찾을 수 없어요.");
        }
        const pct = typeof st.percent === "number" ? st.percent : 0;
        setUploadStatus("재분석 중… " + pct + "%", "busy");
        if (st.message) {
          el.stageBadge.textContent = st.message + " · 재분석";
        }
        if (st.done) {
          if (st.ok === false && !st.session_id) {
            throw new Error(st.message || "재분석에 실패했어요.");
          }
          data = st;
          break;
        }
      }
      applySession(data, "ready", { asNewTab: true });
      const nS = state.sentences.length;
      const nF = state.figures.length;
      setUploadStatus(`재분석 완료 · 문장 ${nS} · 그림 ${nF}`, "");
      setLibraryStatus("");
    } catch (err) {
      setLibraryStatus(String(err.message || err), "error");
      setUploadStatus(String(err.message || err), "error");
    } finally {
      setLoading(false);
    }
  }

  /**
   * 보관 목록에서 삭제 — 로컬+GCS. 열린 탭이면 탭도 닫음.
   * @param {string} cacheId
   * @param {string} titleHint
   */
  async function deleteLibraryPaper(cacheId, titleHint) {
    if (!cacheId) return;
    const label = shortTitle(titleHint || cacheId, 40);
    const ok = window.confirm(
      `「${label}」보관본을 삭제할까요?\n로컬·클라우드 목록에서 지워집니다.`
    );
    if (!ok) return;
    setLibraryStatus("삭제 중…", "busy");
    try {
      const res = await fetch(
        "/api/cache/papers/" + encodeURIComponent(cacheId),
        { method: "DELETE" }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok && res.status !== 404) {
        throw new Error(data.message || "삭제에 실패했습니다.");
      }
      // 열린 탭에 같은 cacheId 있으면 제거
      const openIdx = papers.findIndex(
        (p) => p && p.cacheId && String(p.cacheId) === String(cacheId)
      );
      if (openIdx >= 0) {
        papers.splice(openIdx, 1);
        const reals = realPaperIndices();
        if (reals.length) {
          const prefer =
            reals.find((i) => i >= openIdx) ?? reals[reals.length - 1];
          activePaperIndex = prefer;
          hydrateStateFromPaper(papers[activePaperIndex]);
          uiPhase = "ready";
          render();
          renderPaperTabs();
          updateCacheDeleteBtn();
        } else {
          papers = [];
          activePaperIndex = 0;
          await loadMock();
        }
      }
      await refreshLibraryList();
      setUploadStatus("보관본 삭제됨", "");
    } catch (err) {
      setLibraryStatus(String(err.message || err), "error");
    }
  }

  if (el.libraryBtn) {
    el.libraryBtn.addEventListener("click", () => openLibraryDialog());
  }
  if (el.libraryRefreshBtn) {
    el.libraryRefreshBtn.addEventListener("click", () => refreshLibraryList());
  }
  if (el.libraryDialogClose) {
    el.libraryDialogClose.addEventListener("click", () => {
      if (el.libraryDialog) el.libraryDialog.close();
    });
  }
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
  if (el.citeRefOpenBtn) {
    el.citeRefOpenBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      void openCiteResolvedUrl();
    });
  }
  if (el.citeRefCloseBtn) {
    el.citeRefCloseBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      closeCiteRefPanel();
      const sent = state.sentences[state.sentenceIndex];
      renderCiteRefHints(sent || null);
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

  if (el.authLoginBtn) {
    el.authLoginBtn.addEventListener("click", () => {
      if (!authState.enabled) return;
      openAuthDialog("login");
    });
  }
  if (el.authAccountBtn) {
    el.authAccountBtn.addEventListener("click", () => {
      if (!authState.user) return;
      openAuthDialog("link");
    });
  }
  if (el.usageBtn) {
    el.usageBtn.addEventListener("click", () => {
      void openUsageDialog();
    });
  }
  if (el.usageDialogClose) {
    el.usageDialogClose.addEventListener("click", () => {
      if (el.usageDialog && el.usageDialog.open) el.usageDialog.close();
    });
  }
  if (el.authLogoutBtn) {
    el.authLogoutBtn.addEventListener("click", () => {
      void logoutAuth();
    });
  }
  if (el.authDialogClose) {
    el.authDialogClose.addEventListener("click", () => {
      if (el.authDialog) el.authDialog.close();
    });
  }
  if (el.authKakaoBtn) {
    el.authKakaoBtn.addEventListener("click", () => {
      window.location.href = "/api/auth/kakao/start?mode=login";
    });
  }
  if (el.authLinkKakaoBtn) {
    el.authLinkKakaoBtn.addEventListener("click", () => {
      window.location.href = "/api/auth/kakao/start?mode=link";
    });
  }
  if (el.authGoogleBtn) {
    el.authGoogleBtn.addEventListener("click", () => {
      if (el.authEmailPanel) el.authEmailPanel.hidden = true;
      loadGis("login");
    });
  }
  if (el.authLinkGoogleBtn) {
    el.authLinkGoogleBtn.addEventListener("click", () => {
      if (el.authEmailPanel) el.authEmailPanel.hidden = true;
      loadGis("link");
    });
  }
  if (el.authEmailToggleBtn) {
    el.authEmailToggleBtn.addEventListener("click", () => {
      if (el.googleSignInMount) {
        el.googleSignInMount.hidden = true;
        el.googleSignInMount.innerHTML = "";
      }
      if (el.authEmailPanel) el.authEmailPanel.hidden = false;
    });
  }
  if (el.authLinkEmailBtn) {
    // design/85 — password email-link UI removed; button stays hidden.
    el.authLinkEmailBtn.addEventListener("click", () => {
      setAuthDialogStatus(
        "이메일 연결은 지원하지 않습니다. Google·카카오를 사용하세요.",
        "error"
      );
    });
  }
  if (el.authEmailMagicBtn) {
    el.authEmailMagicBtn.addEventListener("click", () => {
      void requestEmailMagicLink().catch((err) => {
        setAuthDialogStatus(String(err.message || err), "error");
      });
    });
  }

  window.addEventListener("beforeunload", () => {
    try {
      snapshotActivePaper();
      persistReadingProgress();
    } catch (_) {
      /* ignore */
    }
  });

  // design/123 — also persist on tab hide / pagehide (mobile browsers may skip beforeunload).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      try {
        snapshotActivePaper();
        persistReadingProgress();
      } catch (_) {
        /* ignore */
      }
    }
  });
  window.addEventListener("pagehide", () => {
    try {
      snapshotActivePaper();
      persistReadingProgress();
    } catch (_) {
      /* ignore */
    }
  });

  /** @type {boolean} fail-closed until /api/status says otherwise */
  let loginRequiredFlag = true;
  /** design/123 — true → refuse open on bad progress; false = clamp kill switch */
  let progressFailClosedFlag = true;
  let loginGateUnlocked = false;
  let accessWaitingUx = true;
  let accessPollTimer = 0;

  function applyLoginGateChrome(active) {
    document.body.classList.toggle("asr-login-gate", !!active);
    if (el.authDialogClose) {
      // WHY: product = login-only; closing would reveal empty shell.
      el.authDialogClose.hidden = !!active;
    }
  }

  function applyAccessWaitingChrome(active) {
    document.body.classList.toggle("asr-access-waiting", !!active);
    if (el.accessWaitingPanel) el.accessWaitingPanel.hidden = !active;
  }

  function stopAccessPoll() {
    if (accessPollTimer) {
      window.clearInterval(accessPollTimer);
      accessPollTimer = 0;
    }
  }

  function paintAccessWaiting(access) {
    const status = (access && access.status) || "none";
    let hint = "초대 코드를 입력하면 관리자 승인 대기가 됩니다.";
    if (status === "pending") {
      hint = "코드가 확인되었습니다. 관리자 승인을 기다리는 중입니다.";
    } else if (status === "denied") {
      hint = "승인이 거절되었습니다. 새 초대 코드를 다시 입력할 수 있습니다.";
    }
    if (el.accessWaitingHint) el.accessWaitingHint.textContent = hint;
    if (el.accessWaitingStatus) {
      el.accessWaitingStatus.textContent = access
        ? "상태: " + status
        : "";
    }
  }

  async function fetchAccessView() {
    const res = await fetch("/api/access/status", {
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || "access_status_failed");
    }
    return data;
  }

  function startAccessPoll() {
    stopAccessPoll();
    // WHY: admin Allow on another instance — auto enter without refresh tap.
    accessPollTimer = window.setInterval(function () {
      void refreshAccessWaiting(true);
    }, 5000);
  }

  async function refreshAccessWaiting(silent) {
    try {
      const access = await fetchAccessView();
      paintAccessWaiting(access);
      if (!access.gate_enabled || access.can_use_paid) {
        await unlockMainAppFromAccess();
        return true;
      }
      return false;
    } catch (err) {
      // FAIL-CLOSED: keep waiting; never pretend success.
      if (!silent && el.accessWaitingStatus) {
        el.accessWaitingStatus.textContent =
          "상태를 확인하지 못했습니다. 다시 시도하세요.";
      }
      return false;
    }
  }

  async function unlockMainAppFromAccess() {
    stopAccessPoll();
    applyAccessWaitingChrome(false);
    if (!loginGateUnlocked) {
      loginGateUnlocked = true;
      loadMock();
    }
    await pullNotesFromCloud();
  }

  async function enterAppOrAccessWait() {
    // EDGE: capability flag off → skip waiting shell (ops rollback).
    if (!accessWaitingUx) {
      await unlockMainAppFromAccess();
      return;
    }
    try {
      const access = await fetchAccessView();
      // gate off / admin / allowed → main app
      if (!access.gate_enabled || access.can_use_paid) {
        await unlockMainAppFromAccess();
        return;
      }
      applyAccessWaitingChrome(true);
      paintAccessWaiting(access);
      startAccessPoll();
    } catch (_) {
      // FAIL-CLOSED when waiting UX on: show waiting, do not loadMock.
      applyAccessWaitingChrome(true);
      paintAccessWaiting({ status: "none" });
      startAccessPoll();
    }
  }

  async function submitAccessInvite() {
    const raw = el.accessInviteInput ? el.accessInviteInput.value : "";
    const compact = String(raw || "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    if (compact.length !== 8) {
      if (el.accessWaitingStatus) {
        el.accessWaitingStatus.textContent =
          "초대 코드 형식이 올바르지 않습니다.";
      }
      return;
    }
    const res = await fetch("/api/access/invite", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: compact }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      if (el.accessWaitingStatus) {
        el.accessWaitingStatus.textContent =
          data.message || "초대 코드 제출에 실패했습니다.";
      }
      return;
    }
    if (el.accessInviteInput) el.accessInviteInput.value = "";
    const access = data.access || data;
    paintAccessWaiting(access);
    if (!access.gate_enabled || access.can_use_paid) {
      await unlockMainAppFromAccess();
    }
  }

  async function bootWithLoginGate() {
    try {
      const res = await fetch("/api/status", { credentials: "same-origin" });
      const st = await res.json().catch(() => ({}));
      // Missing key → require login (fail-closed for older/partial responses).
      loginRequiredFlag = st.login_required !== false;
      // design/84 — missing key → waiting UX on (fail-closed).
      accessWaitingUx = st.access_waiting_ux !== false;
      // design/123 — missing key → fail-closed (refuse bad progress); explicit false clamps.
      progressFailClosedFlag = st.progress_fail_closed !== false;
    } catch (_) {
      loginRequiredFlag = true;
      accessWaitingUx = true;
      progressFailClosedFlag = true;
    }
    await initAuth();
    const mustGate =
      loginRequiredFlag && !!authState.enabled && !authState.user;
    if (mustGate) {
      applyLoginGateChrome(true);
      applyAccessWaitingChrome(false);
      openAuthDialog("login");
      return;
    }
    applyLoginGateChrome(false);
    if (authState.user) {
      await enterAppOrAccessWait();
      return;
    }
    // Auth disabled / anonymous allowed → main app.
    await unlockMainAppFromAccess();
  }

  if (el.authDialog) {
    el.authDialog.addEventListener("cancel", (ev) => {
      // EDGE: Esc must not dismiss forced login dialog.
      if (document.body.classList.contains("asr-login-gate")) {
        ev.preventDefault();
      }
    });
  }
  if (el.accessInviteSubmit) {
    el.accessInviteSubmit.addEventListener("click", () => {
      void submitAccessInvite().catch(() => {});
    });
  }
  if (el.accessWaitingRefresh) {
    el.accessWaitingRefresh.addEventListener("click", () => {
      void refreshAccessWaiting(false);
    });
  }
  if (el.accessWaitingLogout) {
    el.accessWaitingLogout.addEventListener("click", () => {
      void logoutAuth();
    });
  }

  // design/83+84 — identity then access waiting before reader boot.
  void bootWithLoginGate();
})();
