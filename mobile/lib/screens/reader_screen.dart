import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/cite_refs.dart' as cite;
import '../api/client.dart';
import '../api/document_citation.dart';
import '../api/fig_refs.dart' as fig;
import '../api/figure_pinch_sensitivity.dart';
import '../api/figure_swipe_gate.dart';
import '../api/reading_models.dart';
import '../api/rich_sentence.dart';
import '../state/cite_panel_controller.dart';
import '../state/bookmark_controller.dart';
import '../api/annotation_models.dart';
import '../api/annotation_plain.dart';
import '../api/ai_ask.dart';
import '../state/annotation_controller.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/translate_controller.dart';
import '../state/tts_controller.dart';
import 'shadowing_practice_screen.dart';
import '../api/reader_nav_labels.dart';
import '../api/reader_layout_policy.dart';
import '../widgets/reader_nav_picker.dart';
import '../widgets/annotation_toolbar_sheet.dart';
import '../api/figure_ink_models.dart';
import '../widgets/figure_ink_toolbar.dart';
import '../widgets/swipe_motion.dart';
import '../widgets/reader_wheel.dart';
import '../widgets/annotated_sentence_text.dart';
import '../widgets/upload_status_bar.dart';
import '../state/web_reading_prefs.dart';
import '../state/reader_prefs.dart';
import '../services/full_screen.dart';
import '../widgets/idle_cursor_layer.dart';
import '../services/pane_link.dart';
import 'figure_edit_screen.dart';

/// Split reader: sentence panel + figure panel (design/63) + TTS (design/64).
///
/// INVARIANT: sentence controls never call figure advance and vice versa.
/// TTS never mutates cursors.
/// design/97 — double-tap a panel to fill the screen; double-tap again to restore.
/// design/98 — drag the split bar; magnet at default; edge tension → full-panel snap.
/// design/100 — single tap toggles panel chrome; split mode syncs both frames.
enum _ReaderLayoutMode { split, sentenceOnly, figureOnly }

class ReaderScreen extends StatefulWidget {
  const ReaderScreen({
    super.key,
    required this.library,
    required this.tts,
    required this.client,
    required this.shadowing,
    required this.translate,
    required this.citePanel,
    required this.bookmarks,
    required this.annotations,
    this.pane,
    this.onBack,
  });

  final LibraryController library;
  final TtsController tts;
  final AsrClient client;
  final ShadowingController shadowing;
  final TranslateController translate;
  final CitePanelController citePanel;
  final BookmarkController bookmarks;
  final AnnotationController annotations;
  /// design/415 — the other window of this browser (web only).
  final PaneLink? pane;

  /// design/421 — back to the library. The web shows it as a button: an installed
  /// web app has no browser back button, and the phone has its own back.
  final VoidCallback? onBack;

  @override
  State<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends State<ReaderScreen> {
  static const double _kDefaultFraction = kSplitFractionDefault;
  /// Soft resistance band around default (fraction of height).
  static const double _kMagnetResistanceBand = 0.11;
  /// Pull this far from default → break free to 1:1 tracking (jelly snap).
  static const double _kMagnetEscape = 0.038;
  /// On release, snap to default when still within this distance.
  static const double _kMagnetReleaseSnap = 0.022;
  /// Min drag factor at default (slow pulls still move the bar).
  static const double _kMagnetMinFactor = 0.2;
  static const double _kEdgeSnap = 0.14;
  static const double _kHardMin = 0.02;
  static const double _kHardMax = 0.98;
  static const double _kSplitBar = 16;

  _ReaderLayoutMode _layout = _ReaderLayoutMode.split;
  bool _appliedSavedLayout = false;
  double _sentenceFraction = ReaderPrefs.instance.splitFraction;
  bool _dragging = false;
  bool _inMagnet = false;
  bool _magnetEscaped = false;
  bool _edgePreviewSentence = false;
  bool _edgePreviewFigure = false;
  /// design/100 — shared chrome for sentence + figure headers.
  bool _chromeVisible = true;
  /// design/114 — reset split when a different paper is opened.
  String? _layoutSessionKey;
  /// design/124 — server kill `fig_ref_hints=false` hides chips; missing/error → show.
  bool _figRefHints = true;
  /// design/131 — server kill `caption_full_text=false` restores 2-line …; missing → full.
  bool _captionFullText = true;
  /// design/149 — caption baked into PNG; hide under-image Text when true.
  bool _figureCaptionInImage = true;
  /// design/183 — Intro collapse / first Fig chip expand.
  final ReaderLayoutPolicy _layoutPolicy = ReaderLayoutPolicy();
  bool _readerLayoutAuto = true;
  final FocusNode _keysFocus = FocusNode(debugLabel: 'reader_keys');
  bool _keysVisible = false;
  /// design/414 — a still mouse on a wide web window fades the buttons.
  bool _idleHidden = false;
  Timer? _idleTimer;

  @override
  void initState() {
    super.initState();
    unawaited(WebReadingPrefs.instance.load());
    unawaited(ReaderPrefs.instance.load().then((_) {
      if (!mounted || _dragging || _layout != _ReaderLayoutMode.split) return;
      if (_sentenceFraction != _restFraction) {
        setState(() => _sentenceFraction = _restFraction);
      }
    }));
    widget.library.onSentenceIndexChanged = _onSentenceIndexChanged;
    widget.library.onPastLastSentence = _onPastLastSentence;
    widget.client.fetchStatus().then((st) {
      if (!mounted) return;
      // WHY: explicit false is the kill switch; do not invent a hide on status miss.
      setState(() {
        _figRefHints = st.figRefHints;
        _captionFullText = st.captionFullText;
        _figureCaptionInImage =
            st.mobileFigureCaptionInImage && st.figureCaptionInImage;
        _readerLayoutAuto = st.readerLayoutAuto && st.figRefHints;
        _layoutPolicy.autoEnabled = _readerLayoutAuto;
      });
    }).catchError((_) {
      // EDGE: status unreachable → keep full captions + chips (fail-open for readability).
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Back from the library, focus sits on a library widget; take it again.
    final visible = TickerMode.of(context);
    if (visible && !_keysVisible) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && TickerMode.of(context)) _keysFocus.requestFocus();
      });
    }
    _keysVisible = visible;
  }

  @override
  void dispose() {
    if (widget.library.onSentenceIndexChanged == _onSentenceIndexChanged) {
      widget.library.onSentenceIndexChanged = null;
    }
    if (widget.library.onPastLastSentence == _onPastLastSentence) {
      widget.library.onPastLastSentence = null;
    }
    _idleTimer?.cancel();
    _keysFocus.dispose();
    super.dispose();
  }

  bool _askingDone = false;

  /// design/442 — "next" on the last sentence asks to mark the paper read, as an
  /// e-book does on its last page, instead of wrapping to the first sentence.
  Future<void> _onPastLastSentence() async {
    final lib = widget.library;
    final cid = lib.session?.cacheId.trim() ?? '';
    if (!mounted || cid.isEmpty || _askingDone || !TickerMode.of(context)) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (lib.readDone.isDone(cid)) {
      messenger
        ?..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(
          content: Text('마지막 문장이에요. 다 읽은 논문이에요.'),
          duration: Duration(seconds: 2),
        ));
      return;
    }
    _askingDone = true;
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('다 읽은 논문으로 표시할까요?'),
        content: const Text("보관함과 논문 가져오기 목록에 '다 읽음'이 붙어요."),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('아니요'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('예'),
          ),
        ],
      ),
    );
    _askingDone = false;
    if (yes != true) return;
    await lib.markReadDone(cid, done: true);
    messenger
      ?..hideCurrentSnackBar()
      ..showSnackBar(const SnackBar(
        content: Text('다 읽은 논문으로 표시했어요.'),
        duration: Duration(seconds: 2),
      ));
  }

  void _onPointerMoved() {
    _idleTimer?.cancel();
    if (_idleHidden) setState(() => _idleHidden = false);
    _idleTimer = Timer(kWebChromeIdle, _hideWhenIdle);
  }

  void _hideWhenIdle() {
    if (!mounted || !TickerMode.of(context)) return;
    if (!WebReadingPrefs.instance.autoHide) return;
    if (!webReadingActive(web: kIsWeb, width: MediaQuery.sizeOf(context).width)) return;
    if (widget.annotations.sentencePaintMode) return;
    setState(() => _idleHidden = true);
  }

  /// design/414 — off the web this is [child] untouched.
  Widget _idleChrome(Widget child) {
    if (!kIsWeb) return child;
    return MouseRegion(
      onHover: (_) => _onPointerMoved(),
      onEnter: (_) => _onPointerMoved(),
      child: Listener(
        onPointerDown: (_) => _onPointerMoved(),
        child: IdleCursorLayer(hidden: _idleHidden, child: child),
      ),
    );
  }

  void _pinLayout() => _layoutPolicy.pin();

  /// design/435 — where the split rests: the reader's last bar, else the default.
  double get _restFraction => ReaderPrefs.instance.splitFraction;

  /// design/415 — the figure window shows only figures; the main window shows only
  /// sentences while a figure window is open, or on its way (design/424). Null
  /// leaves the chosen layout.
  _ReaderLayoutMode? get _paneLayout {
    final p = widget.pane;
    if (p == null) return null;
    if (p.role == PaneRole.figure) return _ReaderLayoutMode.figureOnly;
    if (p.figureShown) return _ReaderLayoutMode.sentenceOnly;
    return null;
  }

  _ReaderLayoutMode get _shownLayout => _paneLayout ?? _layout;

  bool _sectionIsTitle(ReadingSession s) {
    final cur = s.currentSentence;
    if (cur == null) return false;
    return cur.section.trim().toLowerCase() == 'title';
  }

  bool _hasCover(ReadingSession s) {
    for (final f in s.figures) {
      final sk = f.slotKey.trim().toLowerCase();
      if (sk.startsWith('title_page:')) return true;
      if (f.caption.trim().toLowerCase().startsWith('title page')) return true;
    }
    return false;
  }

  /// design/459 — same test as the Fig/Table chip row under the sentence.
  bool _sentenceNamesFigure(ReadingSession s, int index) {
    if (!_figRefHints) return false;
    if (index < 0 || index >= s.sentences.length) return false;
    final text = s.sentences[index].text;
    if (text.trim().isEmpty) return false;
    return fig.hintsForSentence(
      text: text,
      captions: s.figures.map((f) => f.caption).toList(),
      slotKeys: s.figures.map((f) => f.slotKey).toList(),
      supplementaryMerged: s.supplementaryMerged,
    ).isNotEmpty;
  }

  int? _thresholdFor(ReadingSession s) {
    final computed = firstFigTableChipSentenceIndex(
      sentences: s.sentences,
      figures: s.figures,
      supplementaryMerged: s.supplementaryMerged,
    );
    return computed ?? s.firstFigTableChipSentenceIndex;
  }

  void _applyDesire(ReaderLayoutDesire desire) {
    switch (desire) {
      case ReaderLayoutDesire.sentenceOnly:
        if (_layout == _ReaderLayoutMode.sentenceOnly) return;
        _layout = _ReaderLayoutMode.sentenceOnly;
        _sentenceFraction = _restFraction;
      case ReaderLayoutDesire.splitDefault:
        if (_layout == _ReaderLayoutMode.split &&
            (_sentenceFraction - _restFraction).abs() < 0.001) {
          return;
        }
        _layout = _ReaderLayoutMode.split;
        _sentenceFraction = _restFraction;
    }
    _edgePreviewSentence = false;
    _edgePreviewFigure = false;
  }

  void _applyAutoLayoutForIndex(ReadingSession s, int sentenceIndex) {
    if (!_layoutPolicy.followsAuto) return;
    if (widget.annotations.sentencePaintMode) return;
    final desire = _layoutPolicy.desireFor(
      sentenceIndex: sentenceIndex,
      sectionIsTitle: _sectionIsTitle(s),
      hasCover: _hasCover(s),
      namesFigure:
          _layoutPolicy.folded && _sentenceNamesFigure(s, sentenceIndex),
    );
    _applyDesire(desire);
  }

  void _onSentenceIndexChanged(int from, int to) {
    if (!mounted) return;
    final s = widget.library.session;
    if (s == null || !s.isValid) return;
    if (!_layoutPolicy.autoEnabled) return;
    if (widget.annotations.sentencePaintMode) return;
    setState(() {
      // design/183 — any real cursor move (chevron, swipe, picker jump)
      // reclaims auto and reapplies desire for `to` vs T (not only ±1 edge).
      _layoutPolicy.unpin();
      _layoutPolicy.threshold = _thresholdFor(s);
      _applyAutoLayoutForIndex(s, to);
    });
  }

  void _ensureLayoutForSession(ReadingSession s) {
    // WHY: key by cacheId only — translate poll mints a new session_id every ~8s
    // and must not reset layout pin / cite accordion (design/183).
    final key = s.cacheId.trim().isNotEmpty ? s.cacheId.trim() : s.sessionId;
    final t = _thresholdFor(s);
    if (_layoutSessionKey == key) {
      // design/183 hazard — SI merge / reanalyze may change T mid-paper.
      if (_layoutPolicy.threshold != t) {
        _layoutPolicy.threshold = t;
        if (_layoutPolicy.followsAuto) {
          _applyAutoLayoutForIndex(s, s.sentenceIndex);
        }
      }
      return;
    }
    _layoutSessionKey = key;
    _chromeVisible = true;
    _dragging = false;
    _inMagnet = false;
    _magnetEscaped = false;
    _edgePreviewSentence = false;
    _edgePreviewFigure = false;
    _layoutPolicy.resetForPaper(
      threshold: t,
      autoEnabled: _readerLayoutAuto,
    );
    if (_layoutPolicy.followsAuto) {
      _applyAutoLayoutForIndex(s, s.sentenceIndex);
    } else {
      _layout = _ReaderLayoutMode.split;
      _sentenceFraction = _restFraction;
    }
  }

  void _toggleChrome() {
    setState(() => _chromeVisible = !_chromeVisible);
  }

  void _toggleSentenceExpand() {
    setState(() {
      _pinLayout();
      if (_layout == _ReaderLayoutMode.sentenceOnly) {
        _layoutPolicy.folded = false;
        _layout = _ReaderLayoutMode.split;
        _sentenceFraction = _restFraction;
      } else {
        _layoutPolicy.folded = true;
        _layout = _ReaderLayoutMode.sentenceOnly;
      }
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  void _toggleFigureExpand() {
    setState(() {
      _pinLayout();
      _layoutPolicy.folded = false;
      if (_layout == _ReaderLayoutMode.figureOnly) {
        _layout = _ReaderLayoutMode.split;
        _sentenceFraction = _restFraction;
      } else {
        _layout = _ReaderLayoutMode.figureOnly;
      }
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  String _qualityBannerMessage(ReadingSession s) {
    final w = s.warnings.where((x) => x.isNotEmpty).toList();
    if (w.isEmpty) {
      return '분석 품질에 주의가 필요합니다. 재분석을 권장합니다.';
    }
    return '분석 품질: ${w.take(3).join(' · ')}';
  }

  /// design/156 — full-screen vertical swipe (split restore stays double-tap).
  void _swipeToSentenceFromFigure() {
    setState(() {
      _pinLayout();
      if (_layout != _ReaderLayoutMode.figureOnly) return;
      _layout = _ReaderLayoutMode.sentenceOnly;
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  void _swipeToFigureFromSentence() {
    setState(() {
      if (_layout != _ReaderLayoutMode.sentenceOnly) return;
      _layoutPolicy.folded = false;
      final s = widget.library.session;
      // design/183 — auto reveal at/after T is split (text+figure), never figureOnly.
      if (s != null && s.isValid && _layoutPolicy.followsAuto) {
        final desire = _layoutPolicy.desireFor(
          sentenceIndex: s.sentenceIndex,
          sectionIsTitle: _sectionIsTitle(s),
          hasCover: _hasCover(s),
        );
        if (desire == ReaderLayoutDesire.splitDefault) {
          _applyDesire(ReaderLayoutDesire.splitDefault);
          return;
        }
      }
      _pinLayout();
      _layout = _ReaderLayoutMode.figureOnly;
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  void _onFigChipPressed(int figureIndex) {
    if (_layout == _ReaderLayoutMode.sentenceOnly) {
      setState(() {
        _pinLayout();
        _layout = _ReaderLayoutMode.split;
        _sentenceFraction = _restFraction;
      });
    }
    widget.library.goToFigureIndex(figureIndex);
  }

  void _onSplitDragStart() {
    setState(() {
      _pinLayout();
      _dragging = true;
      _magnetEscaped = false;
      _layout = _ReaderLayoutMode.split;
    });
  }

  void _onSplitDragUpdate(double deltaDy, double totalH) {
    if (totalH <= _kSplitBar + 1) return;
    final usable = totalH - _kSplitBar;
    setState(() {
      _dragging = true;
      _layout = _ReaderLayoutMode.split;
      final nearEdge = _sentenceFraction < _kEdgeSnap ||
          _sentenceFraction > 1 - _kEdgeSnap;
      final edgeScale = nearEdge ? 0.32 : 1.0;
      final rawDelta = (deltaDy / usable) * edgeScale;

      double next;
      if (_magnetEscaped) {
        next =
            (_sentenceFraction + rawDelta).clamp(_kHardMin, _kHardMax);
        _inMagnet = false;
      } else {
        final dist = (_sentenceFraction - _kDefaultFraction).abs();
        final inBand = dist <= _kMagnetResistanceBand;
        if (inBand) {
          final t = (dist / _kMagnetResistanceBand).clamp(0.0, 1.0);
          final resistance =
              _kMagnetMinFactor + (1.0 - _kMagnetMinFactor) * t * t;
          next = (_sentenceFraction + rawDelta * resistance)
              .clamp(_kHardMin, _kHardMax);
          final newDist = (next - _kDefaultFraction).abs();
          _inMagnet = newDist <= _kMagnetResistanceBand;
          final projected =
              (_sentenceFraction + rawDelta - _kDefaultFraction).abs();
          if (newDist >= _kMagnetEscape || projected >= _kMagnetEscape) {
            _magnetEscaped = true;
            _inMagnet = false;
            next = (_sentenceFraction + rawDelta).clamp(_kHardMin, _kHardMax);
            HapticFeedback.lightImpact();
          }
        } else {
          next =
              (_sentenceFraction + rawDelta).clamp(_kHardMin, _kHardMax);
          _inMagnet = false;
        }
      }

      _sentenceFraction = next;
      _edgePreviewSentence = next >= 1 - _kEdgeSnap;
      _edgePreviewFigure = next <= _kEdgeSnap;
    });
  }

  void _onSplitDragEnd() {
    setState(() {
      _dragging = false;
      _magnetEscaped = false;
      _layoutPolicy.folded = _sentenceFraction >= 1 - _kEdgeSnap;
      if (_sentenceFraction >= 1 - _kEdgeSnap) {
        _layout = _ReaderLayoutMode.sentenceOnly;
        _sentenceFraction = _restFraction;
      } else if (_sentenceFraction <= _kEdgeSnap) {
        _layout = _ReaderLayoutMode.figureOnly;
        _sentenceFraction = _restFraction;
      } else if ((_sentenceFraction - _kDefaultFraction).abs() <=
          _kMagnetReleaseSnap) {
        _sentenceFraction = kSplitFractionDefault;
        _layout = _ReaderLayoutMode.split;
        unawaited(ReaderPrefs.instance.setSplitFraction(kSplitFractionDefault));
      } else {
        _layout = _ReaderLayoutMode.split;
        unawaited(ReaderPrefs.instance.setSplitFraction(_sentenceFraction));
      }
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
      _inMagnet = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final library = widget.library;
    final tts = widget.tts;
    final client = widget.client;
    final shadowing = widget.shadowing;
    final translate = widget.translate;
    return AnimatedBuilder(
      animation: Listenable.merge([
        library,
        tts,
        translate,
        widget.citePanel,
        widget.bookmarks,
        widget.annotations,
        ReaderPrefs.instance,
        if (widget.pane != null) widget.pane!,
      ]),
      builder: (context, _) {
        final s = library.session;
        if (s == null || !s.isValid) {
          // design/225-U — still show upload chrome when auto-open / empty reader.
          return Column(
            children: [
              UploadStatusBar(
                library: library,
                dense: true,
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                onResume: () => unawaited(library.onAppResumed()),
              ),
              const Expanded(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text(
                      'No paper open. Open one from Library\n'
                      '(sentence + figure + TTS).',
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ),
            ],
          );
        }
        _ensureLayoutForSession(s);
        final showKo = translate.enabled;
        final _layoutName = switch (_layout) {
          _ReaderLayoutMode.split => 'split',
          _ReaderLayoutMode.sentenceOnly => 'sentenceOnly',
          _ReaderLayoutMode.figureOnly => 'figureOnly',
        };
        if (!_appliedSavedLayout) {
          _appliedSavedLayout = true;
          final saved = library.readerLayoutMode;
          final restored = switch (saved) {
            'sentenceOnly' => _ReaderLayoutMode.sentenceOnly,
            'figureOnly' => _ReaderLayoutMode.figureOnly,
            _ => _ReaderLayoutMode.split,
          };
          if (restored != _layout) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!mounted) return;
              setState(() => _layout = restored);
            });
          }
        } else if (library.readerLayoutMode != _layoutName) {
          library.readerLayoutMode = _layoutName;
        }
        final showSentence = _shownLayout != _ReaderLayoutMode.figureOnly;
        final showFigure = _shownLayout != _ReaderLayoutMode.sentenceOnly;
        return _readerKeys(_idleChrome(Column(
          children: [
            UploadStatusBar(
              library: library,
              dense: true,
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              onResume: () => unawaited(library.onAppResumed()),
            ),
            if ((library.lastIngestFailure ?? '').trim().isNotEmpty)
              MaterialBanner(
                content: Text(library.lastIngestFailure!),
                leading: Icon(
                  Icons.error_outline,
                  color: Theme.of(context).colorScheme.error,
                ),
                actions: [
                  TextButton(
                    onPressed: () {
                      library.lastIngestFailure = null;
                      library.notifyListeners();
                    },
                    child: const Text('닫기'),
                  ),
                ],
              ),
            if (library.showIngestQualityBanner)
              MaterialBanner(
                content: Text(
                  _qualityBannerMessage(s),
                ),
                leading: const Icon(Icons.info_outline),
                actions: [
                  TextButton(
                    onPressed: () async {
                      final entry = library.paperEntryForCacheId(s.cacheId);
                      if (entry == null) {
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              '보관함에서 이 논문을 찾지 못했습니다. 보관 탭에서 새로고침해 주세요.',
                            ),
                          ),
                        );
                        return;
                      }
                      if (!entry.hasSource) {
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              '원본 PDF가 없어 재분석할 수 없습니다. PDF를 다시 업로드해 주세요.',
                            ),
                          ),
                        );
                        return;
                      }
                      final ok = await library.reanalyzePaper(entry);
                      if (!context.mounted) return;
                      if (ok) {
                        library.dismissIngestQualityBanner();
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('재분석이 완료되었습니다.')),
                        );
                      } else if (library.error != null &&
                          library.error!.isNotEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(library.error!)),
                        );
                      }
                    },
                    child: const Text('재분석'),
                  ),
                  TextButton(
                    onPressed: library.dismissIngestQualityBanner,
                    child: const Text('닫기'),
                  ),
                ],
              ),
            if (library.showAzureLayoutFailedBanner)
              MaterialBanner(
                content: const Text(
                  LibraryController.azureLayoutFailedUserMessage,
                ),
                leading: Icon(
                  Icons.image_not_supported_outlined,
                  color: Theme.of(context).colorScheme.error,
                ),
                actions: [
                  TextButton(
                    onPressed: () async {
                      final entry = library.paperEntryForCacheId(s.cacheId);
                      if (entry == null) {
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              '보관함에서 이 논문을 찾지 못했습니다. 보관 탭에서 새로고침해 주세요.',
                            ),
                          ),
                        );
                        return;
                      }
                      if (!entry.hasSource) {
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              '원본 PDF가 없어 재분석할 수 없습니다. PDF를 다시 업로드해 주세요.',
                            ),
                          ),
                        );
                        return;
                      }
                      final ok = await library.reanalyzePaper(entry);
                      if (!context.mounted) return;
                      if (ok) {
                        library.dismissAzureLayoutFailedBanner();
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('재분석이 완료되었습니다.')),
                        );
                      } else if (library.error != null &&
                          library.error!.isNotEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(library.error!)),
                        );
                      }
                    },
                    child: const Text('재분석'),
                  ),
                  TextButton(
                    onPressed: library.dismissAzureLayoutFailedBanner,
                    child: const Text('닫기'),
                  ),
                ],
              ),
            // design/435 — the tap that hides the sentence buttons hides this row.
            AnimatedSize(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeInOut,
              alignment: Alignment.topCenter,
              child: !_chromeVisible
                  ? const SizedBox(width: double.infinity)
                  : _FadeChrome(
              faded: _idleHidden,
              child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Row(
                children: [
                  if (kIsWeb && widget.onBack != null)
                    IconButton(
                      tooltip: '서재로 (Esc)',
                      onPressed: widget.onBack,
                      icon: const Icon(Icons.arrow_back),
                    ),
                  Expanded(
                    child: Text(
                      s.title.isEmpty ? '(no title)' : s.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                  ),
                  if (shadowing.enabled)
                    TextButton(
                      onPressed: !shadowing.serverAvailable
                          ? null
                          : () async {
                              await shadowing.recordPracticePressed();
                              if (!context.mounted) return;
                              await Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => ShadowingPracticeScreen(
                                    client: client,
                                    library: library,
                                    shadowing: shadowing,
                                    tts: tts,
                                  ),
                                ),
                              );
                              unawaited(library.reloadResumeLabels());
                            },
                      child: const Text('연습'),
                    ),
                  if (widget.pane?.role == PaneRole.main &&
                      webReadingActive(
                          web: kIsWeb, width: MediaQuery.sizeOf(context).width))
                    IconButton(
                      tooltip: widget.pane!.figureOpen
                          ? '그림 창이 열려 있습니다'
                          : '그림 창 따로 열기 (다른 모니터로 옮겨 쓰세요)',
                      onPressed: () {
                        final opened = openFigurePane();
                        unawaited(preparePaneScreens(ask: true));
                        if (opened) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              '브라우저가 새 창을 막았습니다. 창 위쪽 오른쪽의 막힘 표시에서 팝업을 허용해 주세요.',
                            ),
                          ),
                        );
                      },
                      icon: Icon(widget.pane!.figureOpen
                          ? Icons.picture_in_picture_alt
                          : Icons.open_in_new),
                    ),
                  if (kIsWeb && fullScreenSupported)
                    ValueListenableBuilder<bool>(
                      valueListenable: fullScreenOn,
                      builder: (context, on, _) => IconButton(
                        tooltip: on ? '전체 화면 풀기 (Esc)' : '전체 화면 (F11)',
                        onPressed: () => unawaited(toggleFullScreen()),
                        icon: Icon(on ? Icons.fullscreen_exit : Icons.fullscreen),
                      ),
                    ),
                ],
              ),
            ))),
            if (library.shadowingChunksBusy &&
                (library.shadowingChunksCacheId == null ||
                    library.shadowingChunksCacheId == s.cacheId))
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                child: Text(
                  library.shadowingChunksProgress == null ||
                          library.shadowingChunksProgress!.isEmpty
                      ? '연습 구간 준비 중…'
                      : '연습 구간 준비 중 · ${library.shadowingChunksProgress}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            // design/257 — do not show another paper's ensure failure on this reader.
            if (library.shadowingChunksError != null &&
                (library.shadowingChunksCacheId == null ||
                    library.shadowingChunksCacheId == s.cacheId))
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 0),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        library.shadowingChunksError!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: library.shadowingChunksBusy
                          ? null
                          : () => library.retryShadowingChunks(),
                      child: const Text('다시 시도'),
                    ),
                  ],
                ),
              ),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final h = constraints.maxHeight;
                  final showBar = showSentence && showFigure;
                  final bar = showBar ? _kSplitBar : 0.0;
                  final usable = (h - bar).clamp(0.0, h);
                  late final double sentenceH;
                  late final double figureH;
                  if (!showSentence) {
                    sentenceH = 0;
                    figureH = h;
                  } else if (!showFigure) {
                    sentenceH = h;
                    figureH = 0;
                  } else {
                    sentenceH = usable * _sentenceFraction;
                    figureH = usable - sentenceH;
                  }
                  final animMs = _dragging ? 0 : 280;
                  return Stack(
                    children: [
                      Column(
                        children: [
                          // design/115 — NEVER put clipBehavior on Container/
                          // AnimatedContainer without decoration: Flutter does
                          // decoration! and the whole reader body goes blank
                          // (title-only). ClipRect keeps hard edges safely.
                          ClipRect(
                            child: AnimatedContainer(
                              duration: Duration(milliseconds: animMs),
                              curve: Curves.easeInOut,
                              height: sentenceH,
                              child: sentenceH < 1
                                  ? const SizedBox.shrink()
                                  : _SentencePanel(
                                      library: library,
                                      tts: tts,
                                      client: client,
                                      session: s,
                                      citePanel: widget.citePanel,
                                      bookmarks: widget.bookmarks,
                                      annotations: widget.annotations,
                                      showKo: showKo,
                                      showChrome: _chromeVisible,
                                      fadeChrome: _idleHidden,
                                      figRefHints: _figRefHints,
                                      citeCollapsed:
                                          ReaderPrefs.instance.citeCollapsed,
                                      onToggleCiteCollapsed: () => ReaderPrefs
                                          .instance
                                          .setCiteCollapsed(
                                        !ReaderPrefs.instance.citeCollapsed,
                                      ),
                                      onFigChipPressed: _onFigChipPressed,
                                      onToggleChrome: _toggleChrome,
                                      onDoubleTapExpand: _toggleSentenceExpand,
                                      onSwipeToFigure: _layout ==
                                              _ReaderLayoutMode.sentenceOnly
                                          ? _swipeToFigureFromSentence
                                          : null,
                                      slideDir: _slideDirFor(s),
                                      onWheelStep: (d) => _keyMove(d),
                                    ),
                            ),
                          ),
                          // The bar animates with the panes. Inserting it at full
                          // height the moment showBar flips, while the panes are
                          // still animating away from their old heights, made the
                          // column exceed its box by exactly _kSplitBar for a
                          // frame. Sharing the animation keeps the three heights
                          // summing to the available height throughout.
                          ClipRect(
                            child: AnimatedContainer(
                              duration: Duration(milliseconds: animMs),
                              curve: Curves.easeInOut,
                              height: bar,
                              child: bar < 1
                                  ? const SizedBox.shrink()
                                  : _SplitHandle(
                                      height: _kSplitBar,
                                      magnetActive: _inMagnet,
                                      edgePreviewSentence: _edgePreviewSentence,
                                      edgePreviewFigure: _edgePreviewFigure,
                                      onDragStart: _onSplitDragStart,
                                      onDragUpdate: (dy) =>
                                          _onSplitDragUpdate(dy, h),
                                      onDragEnd: _onSplitDragEnd,
                                    ),
                            ),
                          ),
                          ClipRect(
                            child: AnimatedContainer(
                              duration: Duration(milliseconds: animMs),
                              curve: Curves.easeInOut,
                              height: figureH,
                              child: figureH < 1
                                  ? const SizedBox.shrink()
                                  : _FigurePanel(
                                      library: library,
                                      client: client,
                                      session: s,
                                      bookmarks: widget.bookmarks,
                                      annotations: widget.annotations,
                                      showKo: showKo,
                                      showChrome: _chromeVisible,
                                      fadeChrome: _idleHidden,
                                      captionFullText: _captionFullText,
                                      figureCaptionInImage: _figureCaptionInImage,
                                      onToggleChrome: _toggleChrome,
                                      onDoubleTapExpand: _toggleFigureExpand,
                                      onSwipeToSentence: _layout ==
                                              _ReaderLayoutMode.figureOnly
                                          ? _swipeToSentenceFromFigure
                                          : null,
                                      onWheelStep: (d) => _keyMove(d, figure: true),
                                      onLongPressEdit: () {
                                        final cid = s.cacheId.trim();
                                        if (cid.isEmpty) return;
                                        var hasSource = false;
                                        for (final p in library.papers) {
                                          if (p.id == cid) {
                                            hasSource = p.hasSource;
                                            break;
                                          }
                                        }
                                        Navigator.of(context).push(
                                          MaterialPageRoute<void>(
                                            builder: (_) => FigureEditScreen(
                                              client: client,
                                              cacheId: cid,
                                              hasSource: hasSource,
                                              editStash: library.editStash,
                                              paperDisk: library.paperDiskStore,
                                            ),
                                          ),
                                        );
                                      },
                                    ),
                            ),
                          ),
                        ],
                      ),
                      // Smart guide: default split position while near magnet.
                      if (showBar && (_inMagnet || _dragging))
                        Positioned(
                          top: usable * _kDefaultFraction,
                          left: 24,
                          right: 24,
                          child: IgnorePointer(
                            child: AnimatedOpacity(
                              duration: const Duration(milliseconds: 120),
                              opacity: _inMagnet ? 1 : 0.35,
                              child: Container(
                                height: 2,
                                decoration: BoxDecoration(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .primary
                                      .withOpacity(_inMagnet ? 0.85 : 0.4),
                                  borderRadius: BorderRadius.circular(1),
                                ),
                              ),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ],
        )));
      },
    );
  }

  /// design/411 — ←/→ move the sentence (the figure when only the figure shows),
  /// Shift+←/→ move the figure.
  Widget _readerKeys(Widget child) {
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.arrowLeft): () => _keyMove(-1),
        const SingleActivator(LogicalKeyboardKey.arrowRight): () => _keyMove(1),
        const SingleActivator(LogicalKeyboardKey.arrowLeft, shift: true): () =>
            _keyMove(-1, figure: true),
        const SingleActivator(LogicalKeyboardKey.arrowRight, shift: true): () =>
            _keyMove(1, figure: true),
        const SingleActivator(LogicalKeyboardKey.escape): _keyBack,
      },
      child: Focus(
        focusNode: _keysFocus,
        autofocus: true,
        onKeyEvent: _onReaderKey,
        child: child,
      ),
    );
  }

  /// design/419 — on the web, typing while a sentence shows asks AI about it.
  KeyEventResult _onReaderKey(FocusNode node, KeyEvent event) {
    if (!kIsWeb || !node.hasPrimaryFocus) return KeyEventResult.ignored;
    final hw = HardwareKeyboard.instance;
    if (!aiAskOpensOnKey(
      event,
      ctrl: hw.isControlPressed,
      alt: hw.isAltPressed,
      meta: hw.isMetaPressed,
    )) {
      return KeyEventResult.ignored;
    }
    if (!TickerMode.of(context) || widget.annotations.blocksReaderNavigation) {
      return KeyEventResult.ignored;
    }
    // design/434 — the figure window asks about the figure it shows.
    if (_shownLayout == _ReaderLayoutMode.figureOnly) {
      final image = decodeRasterDataUrlCached(
        widget.library.session?.currentFigure?.imageSrc,
      );
      if (image == null) return KeyEventResult.ignored;
      unawaited(() async {
        final ask = await showFigureAiAskDialog(context: context, image: image.bytes);
        if (ask == null || !mounted) return;
        await _askAiAboutFigure(context, image: image, question: ask.question);
      }());
      return KeyEventResult.handled;
    }
    final cur = widget.library.session?.currentSentence;
    if (cur == null) return KeyEventResult.ignored;
    final plain = annotationPlainForSentence(cur.text);
    unawaited(() async {
      final q = await showAiAskTypeDialog(context: context, sentencePlain: plain);
      if (q == null || !mounted) return;
      await _askAiAbout(context, sentencePlain: plain, promptBody: q);
    }());
    return KeyEventResult.handled;
  }

  void _keyBack() {
    if (!kIsWeb || !TickerMode.of(context)) return;
    if (widget.annotations.blocksReaderNavigation) return;
    // The browser spends this Esc on leaving full screen.
    if (fullScreenOn.value || fullScreenJustLeft()) return;
    widget.onBack?.call();
  }

  /// design/471 — the last one-step sentence move, for the slide-in.
  ({int from, int dir, DateTime at})? _slide;

  int _slideDirFor(ReadingSession s) {
    final slide = _slide;
    if (slide == null || s.sentenceIndex == slide.from) return 0;
    if (DateTime.now().difference(slide.at) > const Duration(milliseconds: 600)) {
      return 0;
    }
    return slide.dir;
  }

  void _keyMove(int delta, {bool figure = false}) {
    // The reader stays mounted under the library; keys must not move it unseen.
    if (!TickerMode.of(context)) return;
    if (widget.annotations.blocksReaderNavigation) return;
    final s = widget.library.session;
    if (s == null || !s.isValid) return;
    if (figure || _shownLayout == _ReaderLayoutMode.figureOnly) {
      if (s.figureCount < 1) return;
      unawaited(widget.library.advanceFigure(delta));
      return;
    }
    if (s.sentenceCount < 1) return;
    _slide = (from: s.sentenceIndex, dir: delta.sign, at: DateTime.now());
    unawaited(() async {
      await widget.tts.stop();
      await widget.library.advanceSentence(delta);
    }());
  }
}

/// design/435 — the phone sentence takes its size from settings; the web look
/// keeps its own.
TextStyle _sentenceStyle(WebReadingStyle? web, TextStyle base) => web != null
    ? webSentenceStyle(web, base)
    : phoneSentenceStyle(base);

TextStyle _koStyle(WebReadingStyle? web, TextStyle base) => web != null
    ? webKoStyle(web, base)
    : phoneSentenceStyle(base, px: koPxFor(ReaderPrefs.instance.sentencePx));

/// design/437 — the phone sentence sits a little above the middle of its pane,
/// as on the web; one taller than the pane starts at the top.
Widget _readingColumn(WebReadingStyle? web, double viewHeight, Widget child) {
  if (web != null) return webReadingColumn(web, child);
  return ConstrainedBox(
    constraints: BoxConstraints(minHeight: viewHeight.isFinite ? viewHeight : 0),
    child: Align(
      alignment: Alignment(-1, kWebSentenceAlign.y),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: child,
      ),
    ),
  );
}

/// design/414 — fades the buttons on a still mouse. design/441: their space folds
/// with them, as when a tap hides them, so no empty band is left behind.
class _FadeChrome extends StatelessWidget {
  const _FadeChrome({required this.faded, required this.child});

  final bool faded;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final duration = Duration(milliseconds: faded ? 600 : 150);
    return ClipRect(
      child: AnimatedAlign(
        alignment: Alignment.topCenter,
        heightFactor: faded ? 0 : 1,
        duration: duration,
        curve: Curves.easeInOut,
        child: AnimatedOpacity(
          opacity: faded ? 0 : 1,
          duration: duration,
          child: IgnorePointer(ignoring: faded, child: child),
        ),
      ),
    );
  }
}

/// design/98 — draggable split bar with magnet / edge-snap affordances.
class _SplitHandle extends StatelessWidget {
  const _SplitHandle({
    required this.height,
    required this.onDragStart,
    required this.onDragUpdate,
    required this.onDragEnd,
    this.magnetActive = false,
    this.edgePreviewSentence = false,
    this.edgePreviewFigure = false,
  });

  final double height;
  final VoidCallback onDragStart;
  final ValueChanged<double> onDragUpdate;
  final VoidCallback onDragEnd;
  final bool magnetActive;
  final bool edgePreviewSentence;
  final bool edgePreviewFigure;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Color barColor = scheme.outlineVariant;
    if (magnetActive) {
      barColor = scheme.primary;
    } else if (edgePreviewSentence || edgePreviewFigure) {
      barColor = scheme.tertiary;
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onVerticalDragStart: (_) => onDragStart(),
      onVerticalDragUpdate: (d) => onDragUpdate(d.delta.dy),
      onVerticalDragEnd: (_) => onDragEnd(),
      onVerticalDragCancel: onDragEnd,
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: magnetActive ? 72 : 48,
            height: 4,
            decoration: BoxDecoration(
              color: barColor,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        ),
      ),
    );
  }
}

class _SentencePanel extends StatelessWidget {
  const _SentencePanel({
    required this.library,
    required this.tts,
    required this.client,
    required this.session,
    required this.citePanel,
    required this.bookmarks,
    required this.annotations,
    required this.showKo,
    required this.showChrome,
    this.fadeChrome = false,
    this.figRefHints = true,
    this.citeCollapsed = true,
    this.onToggleCiteCollapsed,
    this.onFigChipPressed,
    this.onToggleChrome,
    this.onDoubleTapExpand,
    this.onSwipeToFigure,
    this.slideDir = 0,
    this.onWheelStep,
  });

  final LibraryController library;
  final TtsController tts;
  final AsrClient client;
  final ReadingSession session;
  final CitePanelController citePanel;
  final BookmarkController bookmarks;
  final AnnotationController annotations;
  final bool showKo;
  final bool showChrome;
  /// design/414 — buttons keep their space but fade out (idle mouse on the web).
  final bool fadeChrome;
  /// design/124 — from /api/status; parent owns fetch.
  final bool figRefHints;
  /// design/183 — local cite sheet collapse (not settings kill).
  final bool citeCollapsed;
  final VoidCallback? onToggleCiteCollapsed;
  final void Function(int figureIndex)? onFigChipPressed;
  final VoidCallback? onToggleChrome;
  final VoidCallback? onDoubleTapExpand;
  /// design/156 — sentence full-screen: swipe up → figure full-screen.
  final VoidCallback? onSwipeToFigure;
  /// design/471 — 1 or -1 right after a wheel or arrow step, else 0.
  final int slideDir;
  final ValueChanged<int>? onWheelStep;

  /// design/430 — a small section name where a section starts: above the
  /// sentence that starts it, or below the one that ends the section before.
  /// Not chrome: it stays when the buttons fade. design/437: on the phone too,
  /// where a tap hides the header that names the section.
  Widget _sectionBreak(
    BuildContext context,
    double fontSize,
    int startIndex, {
    required bool above,
  }) {
    final name = sectionStartLabel(session.sentences, startIndex);
    if (name.isEmpty) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    final line = Expanded(
      child: Divider(color: scheme.outlineVariant.withValues(alpha: 0.6)),
    );
    final gap = fontSize * 0.9;
    return Padding(
      padding: EdgeInsets.only(top: above ? 0 : gap, bottom: above ? gap : 0),
      child: Row(
        children: [
          line,
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              name,
              style: TextStyle(
                fontSize: math.max(12, fontSize * 0.55),
                letterSpacing: 0.6,
                color: scheme.onSurfaceVariant.withValues(alpha: 0.8),
              ),
            ),
          ),
          line,
        ],
      ),
    );
  }

  /// design/414 — the sentence before or after, faded. design/430: across a
  /// section start too; [_sectionBreak] names the new section between them.
  Widget _contextSentence(
    BuildContext context,
    WebReadingStyle web,
    int index, {
    required bool above,
  }) {
    final cur = session.currentSentence;
    final list = session.sentences;
    if (cur == null || index < 0 || index >= list.length) {
      return const SizedBox.shrink();
    }
    final near = list[index];
    if (!near.hasText) return const SizedBox.shrink();
    final gap = web.fontSize * 0.9;
    final style = webContextStyle(
      web,
      Theme.of(context).textTheme.titleMedium ?? const TextStyle(fontSize: 18),
    );
    return Padding(
      padding: EdgeInsets.only(top: above ? 0 : gap, bottom: above ? gap : 0),
      child: ExcludeSemantics(
        child: IgnorePointer(
          child: Opacity(
            opacity: kWebContextOpacity,
            child: Text.rich(
              TextSpan(
                style: style,
                children: annotationRichSpansForSentence(near.text, style),
              ),
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cur = session.currentSentence;
    final header = session.sentenceCount == 0
        ? const SectionHeaderParts(sectionName: 'no sentences', position: 0, total: 0)
        : session.sectionNav.headerPartsFor(session.sentenceIndex);
    final canPick = session.sentenceCount > 0 && session.sectionNav.sectionCount > 0;
    final sentKey =
        session.sectionNav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
    final sentHighlighted = bookmarks.isSentenceBookmarked(sentKey);
    final sectionBadge =
        bookmarks.sectionBadgeCount(session.sectionNav, session.sentenceIndex);
    final bodyWarn = session.warnings.any((w) => w.startsWith('high_body_ratio'));
    final headerLeft = header.sectionName.isEmpty
        ? 'Sentence'
        : (header.sectionName.toLowerCase() == 'body' && bodyWarn
            ? '${header.sectionName} ⚠'
            : header.sectionName);
    final bookmarkHints = BookmarkPickerHints(
      leftBadgeCount: (i) =>
          bookmarks.pickerSectionBadgeCount(session.sectionNav, i),
      rightHighlighted: (left, right) => bookmarks.pickerSentenceHighlighted(
        session.sectionNav,
        left,
        right,
      ),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AnimatedSize(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: showChrome
                ? _FadeChrome(
                    faded: fadeChrome,
                    child: Row(
                    children: [
                      IconButton(
                        tooltip: 'prev sentence',
                        // design/182 — no sentence change while highlight paint armed
                        onPressed: session.sentenceCount == 0 ||
                                annotations.blocksReaderNavigation
                            ? null
                            : () async {
                                await tts.stop();
                                await library.advanceSentence(-1);
                              },
                        icon: const Icon(Icons.chevron_left),
                      ),
                      Expanded(
                        child: ReaderNavHeaderLabel(
                          left: headerLeft,
                          right: session.sentenceCount == 0
                              ? '— / —'
                              : header.rightLabel,
                          enabled: session.sentenceCount > 0,
                          highlighted: sentHighlighted,
                          leftBadgeCount: sectionBadge,
                          onTap: session.sentenceCount == 0
                              ? null
                              : () => _handleSentenceBookmarkTap(
                                    context,
                                    bookmarks: bookmarks,
                                    session: session,
                                  ),
                          onLongPress: canPick &&
                                  !annotations.blocksReaderNavigation
                              ? () async {
                                  final idx = await showSectionNavPicker(
                                    context: context,
                                    nav: session.sectionNav,
                                    currentGlobalIndex: session.sentenceIndex,
                                    bookmarks: bookmarkHints,
                                  );
                                  if (idx == null) return;
                                  await tts.stop();
                                  await library.goToSentenceIndex(idx);
                                }
                              : null,
                        ),
                      ),
                      IconButton(
                        tooltip: 'next sentence',
                        onPressed: session.sentenceCount == 0 ||
                                annotations.blocksReaderNavigation
                            ? null
                            : () async {
                                await tts.stop();
                                await library.advanceSentence(1);
                              },
                        icon: const Icon(Icons.chevron_right),
                      ),
                      if (tts.loading)
                        const SizedBox(
                          width: 24,
                          height: 24,
                          child: Padding(
                            padding: EdgeInsets.all(4),
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        )
                      else
                        IconButton(
                          tooltip: tts.playing ? 'stop TTS' : 'play TTS',
                          onPressed: (cur == null || !cur.hasText)
                              ? null
                              : () async {
                                  if (tts.playing) {
                                    await tts.stop();
                                  } else {
                                    await tts.playCurrentSentence();
                                  }
                                },
                          icon: Icon(
                            tts.playing
                                ? Icons.stop_circle_outlined
                                : Icons.volume_up,
                          ),
                        ),
                    ],
                  ))
                : const SizedBox(width: double.infinity),
          ),
          if (showChrome && tts.error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                tts.error!,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontSize: 12,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          Expanded(
            child: WheelPager(
              onStep: annotations.blocksReaderNavigation ? null : onWheelStep,
              child: _SwipePager(
                pageKey: session.sentenceIndex,
                enabled: session.sentenceCount > 0 &&
                    !annotations.blocksReaderNavigation,
                // design/95+143 — swipe left → next, swipe right → prev
                // design/182 — callbacks null while paint armed (arena + API)
                onPrevious: annotations.blocksReaderNavigation
                    ? null
                    : () async {
                        await tts.stop();
                        await library.advanceSentence(-1);
                      },
                onNext: annotations.blocksReaderNavigation
                    ? null
                    : () async {
                        await tts.stop();
                        await library.advanceSentence(1);
                      },
                onTap: annotations.sentencePaintMode
                    ? () => annotations.clearSentencePaint()
                    : onToggleChrome,
                onDoubleTap:
                    annotations.sentencePaintMode ? null : onDoubleTapExpand,
                onSwipeUp:
                    annotations.sentencePaintMode ? null : onSwipeToFigure,
                // design/182 — do NOT wrap with a drag-absorbing GestureDetector
                // (0.3.170 regression): parent drag recognizers steal the arena
                // from in-sentence paint the same way swipe did in 0.3.166.
                // Nav is blocked via enabled/null callbacks + library gate.
                child: Card(
                  child: Padding(
                  padding: const EdgeInsets.fromLTRB(4, 16, 4, 16),
                  child: WebReadingFrame(
                  builder: (context, web) => LayoutBuilder(
                  builder: (context, box) => SentenceSlideSwitcher(
                    dir: slideDir,
                    child: SingleChildScrollView(
                    // A long sentence scrolled down must not open the next one halfway.
                    key: ValueKey(session.sentenceIndex),
                    padding: EdgeInsets.symmetric(
                        horizontal: web != null ? 12 : phoneColumnInset()),
                    physics: annotations.sentencePaintMode
                        ? const NeverScrollableScrollPhysics()
                        : null,
                    child: cur == null || !cur.hasText
                        ? const Text('No sentence at this index.')
                        : GestureDetector(
                            onLongPress: annotations.sentencePaintMode
                                ? null
                                : () => _handleSentenceAnnotateLongPress(
                                      context,
                                      annotations: annotations,
                                      session: session,
                                    ),
                            child: _readingColumn(web, box.maxHeight, Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (web != null && web.showContext)
                                  _contextSentence(
                                    context,
                                    web,
                                    session.sentenceIndex - 1,
                                    above: true,
                                  ),
                                _sectionBreak(
                                  context,
                                  web?.fontSize ??
                                      ReaderPrefs.instance.sentencePx,
                                    session.sentenceIndex,
                                    above: true,
                                  ),
                                if (cur.isUngrounded)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: Chip(
                                      label: const Text('원문 미확인'),
                                      backgroundColor: Colors.amber.shade100,
                                      visualDensity: VisualDensity.compact,
                                    ),
                                  ),
                                AnnotatedSentenceText(
                                  html: cite
                                      .stripCiteMarkersForDisplay(cur.text),
                                  style: _sentenceStyle(
                                      web,
                                      Theme.of(context).textTheme.titleMedium ??
                                          const TextStyle(fontSize: 18)),
                                  annotations: annotations
                                      .activeForSentenceKey(sentKey),
                                  paintMode:
                                      annotations.isPaintingSentence(sentKey),
                                  paintColor: annotations.paintColor,
                                  previewStart: annotations.paintPreviewStart,
                                  previewEnd: annotations.paintPreviewEnd,
                                  onPaintPreview: (a, b) =>
                                      annotations.setPaintPreview(a, b),
                                  onPaintCancel: () =>
                                      annotations.clearSentencePaint(),
                                  clauseBreaks:
                                      WebReadingPrefs.instance.clauseBreaks,
                                  onPaintCommitted: (start, end) async {
                                    final key = sentKey;
                                    if (key == null) {
                                      annotations.clearSentencePaint();
                                      return;
                                    }
                                    if (!annotations.isPaintingAtIndex(
                                      session.sentenceIndex,
                                    )) {
                                      annotations.clearSentencePaint();
                                      return;
                                    }
                                    final color =
                                        annotations.paintColor ?? 'yellow';
                                    final plain =
                                        annotationPlainForSentence(cur.text);
                                    final ok =
                                        await annotations.addPartialHighlight(
                                      sentenceKey: key,
                                      sentenceId: cur.id,
                                      color: color,
                                      plain: plain,
                                      start: start,
                                      end: end,
                                    );
                                    annotations.clearSentencePaint();
                                    if (ok && context.mounted) {
                                      HapticFeedback.mediumImpact();
                                    }
                                  },
                                ),
                                if (showKo &&
                                    cur.textKo.trim().isNotEmpty) ...[
                                  const SizedBox(height: 12),
                                  richSentenceText(
                                    cite.stripCiteMarkersForDisplay(
                                        cur.textKo),
                                    style: _koStyle(
                                        web,
                                        Theme.of(context).textTheme.bodyMedium ??
                                            const TextStyle(fontSize: 14)),
                                  ),
                                ] else if (showKo &&
                                    (library.translateBackfillBusy ||
                                        session.translatePending)) ...[
                                  const SizedBox(height: 12),
                                  Text(
                                    '번역 준비 중…',
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodyMedium
                                        ?.copyWith(
                                          color: Theme.of(context)
                                              .colorScheme
                                              .onSurfaceVariant,
                                        ),
                                  ),
                                ],
                                _sectionBreak(
                                  context,
                                  web?.fontSize ??
                                      ReaderPrefs.instance.sentencePx,
                                    session.sentenceIndex + 1,
                                    above: false,
                                  ),
                                if (web != null && web.showContext)
                                  _contextSentence(
                                    context,
                                    web,
                                    session.sentenceIndex + 1,
                                    above: false,
                                  ),
                              ],
                            )),
                          ),
                  )))),
                ),
              ),
            ),
            ),
          ),
          if (shouldShowThisPaperPanel(
            session: session,
            citePanelEnabled: citePanel.enabled,
            citePanelServerAvailable: citePanel.serverAvailable,
            thisPaperServerAvailable: citePanel.thisPaperServerAvailable,
          ))
            _ThisPaperPanel(
              client: client,
              citation: effectiveCitation(session),
            ),
          // design/139 — web-parity: dedicated chip row BELOW sentence frame (not inside body scroll).
          ..._figRefChipRow(context),
          if (citePanel.enabled && citePanel.serverAvailable)
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // design/429 — folded means "not now", so it fades with the buttons.
                // design/435 — and goes with them when a tap hides them.
                AnimatedSize(
                  duration: const Duration(milliseconds: 180),
                  curve: Curves.easeInOut,
                  alignment: Alignment.topCenter,
                  child: !showChrome && citeCollapsed
                      ? const SizedBox(width: double.infinity)
                      : _FadeChrome(
                  faded: fadeChrome && citeCollapsed,
                  child: InkWell(
                  onTap: onToggleCiteCollapsed,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 4, 12, 4),
                    child: Row(
                      children: [
                        Icon(
                          citeCollapsed
                              ? Icons.expand_more
                              : Icons.expand_less,
                          size: 20,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '참고문헌',
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                      ],
                    ),
                  ),
                ),
                )),
                if (!citeCollapsed)
                  _CiteRefPanel(
                    client: client,
                    session: session,
                  ),
              ],
            ),
        ],
      ),
    );
  }

  List<Widget> _figRefChipRow(BuildContext context) {
    // Kill: /api/status fig_ref_hints=false → no chips (design/124 · 139).
    if (!figRefHints) return const [];
    final cur = session.currentSentence;
    if (cur == null || !cur.hasText) return const [];
    final captions = session.figures.map((f) => f.caption).toList();
    final slotKeys = session.figures.map((f) => f.slotKey).toList();
    final hints = fig.hintsForSentence(
      text: cur.text,
      captions: captions,
      slotKeys: slotKeys,
      supplementaryMerged: session.supplementaryMerged,
    );
    if (hints.isEmpty) return const [];
    final scheme = Theme.of(context).colorScheme;
    return [
      Padding(
        padding: const EdgeInsets.fromLTRB(8, 6, 8, 2),
        child: Wrap(
          spacing: 6,
          runSpacing: 4,
          children: [
            for (final h in hints)
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  // WHY: ghost chip like web .fig-ref-chip (transparent + border).
                  foregroundColor: h.figureIndex == session.figureIndex
                      ? scheme.onSurface
                      : scheme.onSurfaceVariant,
                  side: BorderSide(
                    color: h.figureIndex == session.figureIndex
                        ? scheme.outline
                        : scheme.outlineVariant,
                  ),
                  backgroundColor: Colors.transparent,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                onPressed: () {
                  // WHY: figure only — sentence index must stay (design/28 · 139).
                  // design/183 — reveal split if sentence-only so the jump is visible.
                  final go = onFigChipPressed;
                  if (go != null) {
                    go(h.figureIndex);
                  } else {
                    library.goToFigureIndex(h.figureIndex);
                  }
                },
                child: Text(
                  '${h.ref} →',
                  style: const TextStyle(fontSize: 12, letterSpacing: 0.2),
                ),
              ),
          ],
        ),
      ),
    ];
  }
}

/// design/157 — single bibliographic row for the paper being read (Title 1/N).
class _ThisPaperPanel extends StatefulWidget {
  const _ThisPaperPanel({
    required this.client,
    required this.citation,
  });

  final AsrClient client;
  final DocumentCitation citation;

  @override
  State<_ThisPaperPanel> createState() => _ThisPaperPanelState();
}

class _ThisPaperPanelState extends State<_ThisPaperPanel> {
  bool _busy = false;
  String? _inlineError;

  Future<void> _open() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _inlineError = null;
    });
    try {
      final doi = widget.citation.doi.trim();
      if (doi.isNotEmpty) {
        final uri = Uri.parse('https://doi.org/$doi');
        final launched =
            await launchUrl(uri, mode: LaunchMode.externalApplication);
        if (!launched && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('브라우저를 열 수 없습니다.')),
          );
        }
        return;
      }
      final result = await widget.client.resolveCite(widget.citation.text);
      if (!result.ok || result.url.isEmpty) {
        final msg = result.message.isNotEmpty
            ? result.message
            : (result.error.isNotEmpty ? result.error : 'resolve_failed');
        setState(() => _inlineError = msg);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('이 논문 링크를 열 수 없습니다: $msg')),
          );
        }
        return;
      }
      final uri = Uri.tryParse(result.url);
      if (uri == null) {
        setState(() => _inlineError = 'bad_url');
        return;
      }
      final launched =
          await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('브라우저를 열 수 없습니다.')),
        );
      }
    } catch (e) {
      setState(() => _inlineError = e.toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('이 논문 링크 오류: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.citation.isVisible) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 2),
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Text(
                '이 논문',
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            if (_inlineError != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                child: Text(
                  _inlineError!,
                  style: TextStyle(color: scheme.error, fontSize: 11),
                ),
              ),
            ListTile(
              dense: true,
              visualDensity: VisualDensity.compact,
              enabled: !_busy,
              leading: Icon(
                Icons.article_outlined,
                size: 20,
                color: scheme.onSurfaceVariant,
              ),
              title: Text(
                widget.citation.text,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12),
              ),
              subtitle: widget.citation.doi.isNotEmpty
                  ? Text(
                      'DOI ${widget.citation.doi}',
                      style: const TextStyle(fontSize: 10),
                    )
                  : null,
              onTap: _open,
            ),
          ],
        ),
      ),
    );
  }
}

/// design/148 — scrollable bibliography rows for current sentence cite numbers.
class _CiteRefPanel extends StatefulWidget {
  const _CiteRefPanel({
    required this.client,
    required this.session,
  });

  final AsrClient client;
  final ReadingSession session;

  @override
  State<_CiteRefPanel> createState() => _CiteRefPanelState();
}

class _CiteRefPanelState extends State<_CiteRefPanel> {
  int? _selectedN;
  int _sentenceIndex = -1;
  bool _busy = false;
  String? _inlineError;

  @override
  void initState() {
    super.initState();
    _sentenceIndex = widget.session.sentenceIndex;
  }

  @override
  void didUpdateWidget(covariant _CiteRefPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.session.sentenceIndex != _sentenceIndex) {
      _sentenceIndex = widget.session.sentenceIndex;
      _selectedN = null;
      _inlineError = null;
    }
  }

  Future<void> _openRow(cite.CiteRefEntry entry) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _selectedN = entry.n;
      _inlineError = null;
    });
    try {
      final result = await widget.client.resolveCite(entry.text);
      if (!result.ok || result.url.isEmpty) {
        final msg = result.message.isNotEmpty
            ? result.message
            : (result.error.isNotEmpty ? result.error : 'resolve_failed');
        setState(() => _inlineError = msg);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('참고문헌 링크를 열 수 없습니다: $msg')),
          );
        }
        return;
      }
      final uri = Uri.tryParse(result.url);
      if (uri == null) {
        setState(() => _inlineError = 'bad_url');
        return;
      }
      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('브라우저를 열 수 없습니다.')),
        );
      }
    } catch (e) {
      setState(() => _inlineError = e.toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('참고문헌 링크 오류: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cur = widget.session.currentSentence;
    if (cur == null || !cur.hasText) return const SizedBox.shrink();
    final hints = cite.hintsForSentence(
      text: cur.text,
      bibliography: widget.session.references,
    );
    if (hints.isEmpty) {
      if (widget.session.references.isEmpty) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 2),
          child: Text(
            '참고문헌을 찾지 못했습니다. 재분석하면 표시될 수 있습니다.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        );
      }
      // design/183 — stay expanded; this sentence simply has no cite chips.
      return Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
        child: Text(
          '이 문장에 표시할 인용이 없습니다.',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
        ),
      );
    }

    final maxH = MediaQuery.sizeOf(context).height * 0.22;
    final scheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 2),
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Text(
                'References',
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            if (_inlineError != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                child: Text(
                  _inlineError!,
                  style: TextStyle(color: scheme.error, fontSize: 11),
                ),
              ),
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxH),
              child: ListView.separated(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 6),
                itemCount: hints.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, i) {
                  final h = hints[i];
                  final selected = _selectedN == h.n;
                  return ListTile(
                    dense: true,
                    visualDensity: VisualDensity.compact,
                    enabled: !_busy,
                    selected: selected,
                    leading: Text(
                      '[${h.n}]',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: selected ? scheme.primary : scheme.onSurface,
                      ),
                    ),
                    title: Text(
                      h.text,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12),
                    ),
                    onTap: () => _openRow(h),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FigurePanel extends StatelessWidget {
  const _FigurePanel({
    required this.library,
    required this.client,
    required this.session,
    required this.bookmarks,
    required this.annotations,
    required this.showKo,
    required this.showChrome,
    this.fadeChrome = false,
    this.captionFullText = true,
    this.figureCaptionInImage = true,
    this.onToggleChrome,
    this.onDoubleTapExpand,
    this.onLongPressEdit,
    this.onSwipeToSentence,
    this.onWheelStep,
  });

  final LibraryController library;
  final AsrClient client;
  /// design/471 — wheel turns figures; Ctrl+wheel zooms.
  final ValueChanged<int>? onWheelStep;
  final ReadingSession session;
  final BookmarkController bookmarks;
  final AnnotationController annotations;
  final bool showKo;
  final bool showChrome;
  final bool fadeChrome;
  /// design/131 — false restores 2-line ellipsis (server kill / old clients).
  final bool captionFullText;
  /// design/149 — when true, caption is in PNG; hide Text under image.
  final bool figureCaptionInImage;
  final VoidCallback? onToggleChrome;
  final VoidCallback? onDoubleTapExpand;
  /// design/151 — long-press figure panel → overlay editor.
  final VoidCallback? onLongPressEdit;
  /// design/156 — figure full-screen: swipe down → sentence full-screen.
  final VoidCallback? onSwipeToSentence;

  @override
  Widget build(BuildContext context) {
    final cur = session.currentFigure;
    final header = session.figureCount == 0
        ? const FigureHeaderParts(
            kindLabel: 'no figures', numberLabel: '', totalLabel: '')
        : session.figureNav.headerPartsFor(
            session.figureIndex,
            totalFigures: session.figureCount,
          );
    final canPick =
        session.figureCount > 0 && session.figureNav.hasPicker;
    final figKey =
        session.figureNav.figureBookmarkKeyForCarousel(session.figureIndex);
    final figHighlighted = bookmarks.isFigureBookmarked(figKey);
    final kindBadge =
        bookmarks.kindBadgeCount(session.figureNav, session.figureIndex);
    final bookmarkHints = BookmarkPickerHints(
      leftBadgeCount: (i) => bookmarks.pickerKindBadgeCount(session.figureNav, i),
      rightHighlighted: (left, right) => bookmarks.pickerFigureHighlighted(
        session.figureNav,
        left,
        right,
      ),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AnimatedSize(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: showChrome
                ? _FadeChrome(
                    faded: fadeChrome,
                    child: Row(
                    children: [
                      IconButton(
                        tooltip: 'prev figure',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => library.advanceFigure(-1),
                        icon: const Icon(Icons.chevron_left),
                      ),
                      Expanded(
                        child: ReaderNavHeaderLabel(
                          left: header.kindLabel.isEmpty
                              ? 'Figure'
                              : header.kindLabel,
                          right: session.figureCount == 0
                              ? '— / —'
                              : header.rightLabel,
                          enabled: session.figureCount > 0,
                          highlighted: figHighlighted,
                          leftBadgeCount: kindBadge,
                          onTap: session.figureCount == 0
                              ? null
                              : () => _handleFigureBookmarkTap(
                                    context,
                                    bookmarks: bookmarks,
                                    session: session,
                                  ),
                          onLongPress: canPick
                              ? () async {
                                  final idx = await showFigureNavPicker(
                                    context: context,
                                    nav: session.figureNav,
                                    currentCarouselIndex: session.figureIndex,
                                    bookmarks: bookmarkHints,
                                  );
                                  if (idx == null) return;
                                  await library.goToFigureIndex(idx);
                                }
                              : null,
                        ),
                      ),
                      IconButton(
                        tooltip: 'next figure',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => library.advanceFigure(1),
                        icon: const Icon(Icons.chevron_right),
                      ),
                      IconButton(
                        tooltip: annotations.figureInkMode ? '잉크 끄기' : '잉크',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => annotations.toggleFigureInkMode(),
                        icon: Icon(
                          annotations.figureInkMode
                              ? Icons.draw
                              : Icons.draw_outlined,
                        ),
                      ),
                    ],
                  ))
                : const SizedBox(width: double.infinity),
          ),
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.deferToChild,
              onLongPress: onLongPressEdit,
              child: Card(
                clipBehavior: Clip.antiAlias,
                child: cur == null
                  ? GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: onToggleChrome,
                      child: const Center(child: Text('No figure.')),
                    )
                  : Stack(
                      fit: StackFit.expand,
                      children: [
                        Column(
                      children: [
                        Expanded(
                          child: WheelPager(
                            onStep: annotations.blocksReaderNavigation
                                ? null
                                : onWheelStep,
                            child: _FigureImage(
                            src: cur.imageSrc,
                            expectImage: session.figureCount > 0,
                            figureKey: figKey,
                            annotations: annotations,
                            swipeEnabled: session.figureCount > 0 &&
                                !annotations.figureInkMode,
                            onPrevious: () => library.advanceFigure(-1),
                            onNext: () => library.advanceFigure(1),
                            onTap: onToggleChrome,
                            onDoubleTapExpand: onDoubleTapExpand,
                            onSwipeToSentence: onSwipeToSentence,
                          ),
                          ),
                        ),
                        if (!figureCaptionInImage &&
                            (cur.caption.trim().isNotEmpty ||
                                (showKo && cur.captionKo.trim().isNotEmpty)))
                          // design/131 — full caption: wrap + scroll (no 2-line …).
                          // WHY ConstrainedBox: unbounded Column must not crush the image.
                          // Kill: when server sends caption_full_text=false, keep 2-line ellipsis.
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: ConstrainedBox(
                              constraints: BoxConstraints(
                                maxHeight:
                                    MediaQuery.sizeOf(context).height * 0.22,
                              ),
                              child: SingleChildScrollView(
                                child: Text(
                                  (showKo && cur.captionKo.trim().isNotEmpty)
                                      ? cite.stripCiteMarkersForDisplay(
                                          cur.captionKo,
                                        )
                                      : cite.stripCiteMarkersForDisplay(
                                          cur.caption,
                                        ),
                                  maxLines: captionFullText ? null : 2,
                                  overflow: captionFullText
                                      ? TextOverflow.visible
                                      : TextOverflow.ellipsis,
                                  softWrap: true,
                                  style:
                                      Theme.of(context).textTheme.bodySmall,
                                ),
                              ),
                            ),
                          ),
                      ],
                        ),
                        Positioned(
                          top: 0,
                          left: 0,
                          right: 0,
                          child: FigureInkToolbar(
                            expanded: annotations.figureInkMode &&
                                session.figureCount > 0,
                            tool: annotations.figureInkTool,
                            colorHex: annotations.figureInkColor,
                            onToolChanged: annotations.setFigureInkTool,
                            onColorChanged: annotations.setFigureInkColor,
                          ),
                        ),
                      ],
                    ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _FigureInkOverlay extends StatefulWidget {
  const _FigureInkOverlay({
    required this.figureKey,
    required this.annotations,
    required this.child,
  });

  final String? figureKey;
  final AnnotationController annotations;
  final Widget child;

  @override
  State<_FigureInkOverlay> createState() => _FigureInkOverlayState();
}

class _FigureInkOverlayState extends State<_FigureInkOverlay> {
  List<Offset> _stroke = [];

  Future<void> _eraseAt(Offset local, double w, double h) async {
    final key = widget.figureKey;
    if (key == null || w <= 0 || h <= 0) return;
    await widget.annotations.eraseFigureInkNear(
      figureKey: key,
      nx: local.dx / w,
      ny: local.dy / h,
    );
  }

  @override
  Widget build(BuildContext context) {
    final key = widget.figureKey;
    final inkEvents = widget.annotations.activeForFigureKey(key);
    final inkMode = widget.annotations.figureInkMode;
    final tool = widget.annotations.figureInkTool;
    final strokeColor = figureInkStrokeColor(widget.annotations.figureInkColor);
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        return Stack(
          fit: StackFit.expand,
          children: [
            widget.child,
            if (inkEvents.isNotEmpty)
              IgnorePointer(
                child: CustomPaint(
                  painter: _InkPathsPainter(
                    events: inkEvents,
                    size: Size(w, h),
                  ),
                ),
              ),
            if (inkMode && tool == FigureInkTool.pen)
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onPanStart: (d) => _stroke = [d.localPosition],
                onPanUpdate: (d) =>
                    setState(() => _stroke.add(d.localPosition)),
                onPanEnd: (_) async {
                  if (key == null || _stroke.length < 2) {
                    setState(() => _stroke = []);
                    return;
                  }
                  if (w <= 0 || h <= 0) return;
                  final points = _stroke
                      .map((p) => [p.dx / w, p.dy / h])
                      .toList(growable: false);
                  await widget.annotations.addFigureInkPath(
                    figureKey: key,
                    points: points,
                  );
                  if (mounted) setState(() => _stroke = []);
                },
                child: CustomPaint(
                  painter: _LiveStrokePainter(_stroke, color: strokeColor),
                ),
              ),
            if (inkMode && tool == FigureInkTool.eraser)
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onPanStart: (d) => _eraseAt(d.localPosition, w, h),
                onPanUpdate: (d) => _eraseAt(d.localPosition, w, h),
                child: const SizedBox.expand(),
              ),
          ],
        );
      },
    );
  }
}

class _InkPathsPainter extends CustomPainter {
  _InkPathsPainter({required this.events, required this.size});

  final List<AnnotationEvent> events;
  final Size size;

  @override
  void paint(Canvas canvas, Size canvasSize) {
    for (final ev in events) {
      for (final path in ev.paths) {
        final pts = path['points'];
        if (pts is! List || pts.length < 2) continue;
        final colorRaw = '${path['color'] ?? ev.color}';
        final paint = Paint()
          ..color = figureInkStrokeColor(colorRaw)
          ..strokeWidth = kFigureInkStrokeWidth
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round;
        final pathObj = Path();
        for (var i = 0; i < pts.length; i++) {
          final pt = pts[i];
          if (pt is! List || pt.length < 2) continue;
          final x = (pt[0] as num).toDouble() * canvasSize.width;
          final y = (pt[1] as num).toDouble() * canvasSize.height;
          if (i == 0) {
            pathObj.moveTo(x, y);
          } else {
            pathObj.lineTo(x, y);
          }
        }
        canvas.drawPath(pathObj, paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _InkPathsPainter oldDelegate) =>
      oldDelegate.events != events || oldDelegate.size != size;
}

class _LiveStrokePainter extends CustomPainter {
  _LiveStrokePainter(this.points, {required this.color});

  final List<Offset> points;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final paint = Paint()
      ..color = color
      ..strokeWidth = kFigureInkStrokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (var i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _LiveStrokePainter oldDelegate) =>
      oldDelegate.points != points;
}

class _FigureImage extends StatelessWidget {
  const _FigureImage({
    required this.src,
    this.expectImage = false,
    this.figureKey,
    this.annotations,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
    this.onTap,
    this.onDoubleTapExpand,
    this.onSwipeToSentence,
  });

  final String src;
  /// 0.3.123 — empty src with known figures → loading, not permanent miss.
  final bool expectImage;
  final String? figureKey;
  final AnnotationController? annotations;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTapExpand;
  final VoidCallback? onSwipeToSentence;

  @override
  Widget build(BuildContext context) {
    if (src.isEmpty) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Center(
          child: expectImage
              ? const Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 28,
                      height: 28,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    SizedBox(height: 12),
                    Text('그림 불러오는 중…'),
                  ],
                )
              : const Text('이미지 없음'),
        ),
      );
    }
    final decoded = decodeRasterDataUrlCached(src);
    if (decoded != null) {
      return _ZoomableFigureFrame(
        key: ValueKey<String>('fig-mem-${src.length}-${src.hashCode}'),
        figureKey: figureKey,
        annotations: annotations,
        swipeEnabled: swipeEnabled,
        onPrevious: onPrevious,
        onNext: onNext,
        onTap: onTap,
        onDoubleTapExpand: onDoubleTapExpand,
        onSwipeToSentence: onSwipeToSentence,
        child: Image.memory(
          decoded.bytes,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
          gaplessPlayback: true,
        ),
      );
    }
    if (src.startsWith('http://') || src.startsWith('https://')) {
      return _ZoomableFigureFrame(
        key: ValueKey<String>('fig-net-${src.hashCode}'),
        figureKey: figureKey,
        annotations: annotations,
        swipeEnabled: swipeEnabled,
        onPrevious: onPrevious,
        onNext: onNext,
        onTap: onTap,
        onDoubleTapExpand: onDoubleTapExpand,
        onSwipeToSentence: onSwipeToSentence,
        child: Image.network(
          src,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
          gaplessPlayback: true,
          errorBuilder: (_, __, ___) =>
              const Center(child: Text('이미지 없음')),
        ),
      );
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: const Center(
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text(
            '이미지 없음 (이 형식은 미리보기 불가 · 캡션만)',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}

/// design/95+143 — horizontal swipe: left→next, right→prev (figures only when not zoomed).
/// design/100 — single tap toggles chrome (deferred so double-tap expand wins).
class _SwipePager extends StatefulWidget {
  const _SwipePager({
    required this.child,
    required this.onPrevious,
    required this.onNext,
    this.onTap,
    this.onDoubleTap,
    this.onSwipeUp,
    this.enabled = true,
    this.pageKey,
  });

  final Widget child;
  final Future<void> Function()? onPrevious;
  final Future<void> Function()? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTap;
  /// design/156 — sentence full-screen only: swipe up → figure panel.
  final VoidCallback? onSwipeUp;
  final bool enabled;
  /// design/459 — changes when the next page is in [child].
  final Object? pageKey;

  @override
  State<_SwipePager> createState() => _SwipePagerState();
}

class _SwipePagerState extends State<_SwipePager>
    with TickerProviderStateMixin {
  static const double _minDistance = 56;
  static const double _minVelocity = 180;
  static const double _minVerticalDistance = 88;
  double _dx = 0;
  double _dy = 0;
  double _visual = 0;
  double _width = 1;
  AnimationController? _motion;
  int _motionGen = 0;
  /// design/459 — the page flew off and waits for [_SwipePager.pageKey] to move.
  bool _parked = false;
  Timer? _parkTimer;

  @override
  void didUpdateWidget(covariant _SwipePager oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_parked && widget.pageKey != oldWidget.pageKey) {
      _parkTimer?.cancel();
      _parked = false;
      _visual = 0;
    }
  }

  @override
  void dispose() {
    _parkTimer?.cancel();
    _motion?.dispose();
    super.dispose();
  }

  void _stopMotion() {
    _motionGen++;
    _motion?.dispose();
    _motion = null;
    _parkTimer?.cancel();
    _parked = false;
  }

  void _springBack(double velocity) {
    _stopMotion();
    final from = _visual;
    if (from.abs() < 0.5 && velocity.abs() < 8) {
      if (mounted) setState(() => _visual = 0);
      return;
    }
    final gen = _motionGen;
    final sim = SpringSimulation(
      const SpringDescription(mass: 0.55, stiffness: 280, damping: 20),
      from,
      0,
      velocity,
    );
    final ctrl = AnimationController.unbounded(vsync: this);
    _motion = ctrl;
    ctrl.addListener(() {
      if (!mounted || gen != _motionGen) return;
      setState(() => _visual = ctrl.value);
    });
    ctrl.animateWith(sim).whenComplete(() {
      if (!mounted || gen != _motionGen) return;
      setState(() => _visual = 0);
    });
  }

  void _flyOff(double target, VoidCallback then) {
    _stopMotion();
    final gen = _motionGen;
    final ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 220),
    );
    _motion = ctrl;
    final anim = Tween<double>(begin: _visual, end: target).animate(
      CurvedAnimation(parent: ctrl, curve: Curves.easeIn),
    );
    ctrl.addListener(() {
      if (!mounted || gen != _motionGen) return;
      setState(() => _visual = anim.value);
    });
    ctrl.forward().whenComplete(() {
      if (!mounted || gen != _motionGen) return;
      _parked = true;
      _parkTimer = Timer(kSwipeParkLimit, () {
        if (mounted && _parked) _springBack(0);
      });
      then();
    });
  }

  void _handleHorizontalDragEnd(DragEndDetails details) {
    if (!widget.enabled) return;
    // design/183 — one gesture → one action (avoid advance+figureOnly race).
    if (_dy.abs() > _dx.abs()) {
      _dx = 0;
      _springBack(0);
      return;
    }
    final v = details.primaryVelocity ?? 0;
    // design/143 — gallery convention: finger left → next, right → previous.
    final goNext = _dx < -_minDistance || v < -_minVelocity;
    final goPrev = _dx > _minDistance || v > _minVelocity;
    final finger = _dx;
    _dx = 0;
    _dy = 0;
    if (goPrev && widget.onPrevious != null) {
      _flyOff(flingTarget(finger == 0 ? 1 : finger, _width), () {
        widget.onPrevious!();
      });
    } else if (goNext && widget.onNext != null) {
      _flyOff(flingTarget(finger == 0 ? -1 : finger, _width), () {
        widget.onNext!();
      });
    } else {
      _springBack(v);
    }
  }

  void _handleVerticalDragEnd(DragEndDetails details) {
    if (!widget.enabled || widget.onSwipeUp == null) return;
    // design/183 — horizontal sentence turn wins over 156 figure expand.
    if (_dx.abs() >= _dy.abs()) {
      _dy = 0;
      return;
    }
    final v = details.primaryVelocity ?? 0;
    // design/156 — finger up → reveal figure (split under auto @T, else full).
    final goUp = _dy < -_minVerticalDistance || v < -_minVelocity;
    _dy = 0;
    _dx = 0;
    if (_visual.abs() > 0.5) _springBack(0);
    if (goUp) {
      widget.onSwipeUp!();
    }
  }

  @override
  Widget build(BuildContext context) {
    // design/182 — when disabled (sentence paint mode), do NOT register
    // horizontal/vertical drag handlers at all. Leaving them attached still
    // wins the gesture arena and blocks in-sentence highlight drag even if
    // onEnd is a no-op.
    final swipesOn = widget.enabled;
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth > 0) _width = constraints.maxWidth;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: widget.onTap,
          onDoubleTap: widget.onDoubleTap,
          onHorizontalDragStart: !swipesOn
              ? null
              : widget.onSwipeUp == null
                  ? (_) {
                      _stopMotion();
                      _dx = 0;
                    }
                  : (_) {
                      _stopMotion();
                      _dx = 0;
                      _dy = 0;
                    },
          onHorizontalDragUpdate: !swipesOn
              ? null
              : (d) {
                  _dx += d.delta.dx;
                  setState(() {
                    _visual = rubberBandOffset(_dx, _width);
                  });
                },
          onHorizontalDragEnd: !swipesOn ? null : _handleHorizontalDragEnd,
          onVerticalDragStart: !swipesOn || widget.onSwipeUp == null
              ? null
              : (_) {
                  _dx = 0;
                  _dy = 0;
                },
          onVerticalDragUpdate: !swipesOn || widget.onSwipeUp == null
              ? null
              : (d) => _dy += d.delta.dy,
          onVerticalDragEnd: !swipesOn || widget.onSwipeUp == null
              ? null
              : _handleVerticalDragEnd,
          child: Transform.translate(
            offset: Offset(_visual, 0),
            child: SizedBox(
              width: constraints.maxWidth,
              height: constraints.maxHeight,
              child: widget.child,
            ),
          ),
        );
      },
    );
  }
}

/// design/94+95+97+100+116+117+118 — full-frame zoom; swipe at 1×; tap chrome; double-tap expand.
///
/// design/116 — do NOT put [onHorizontalDrag*] on a parent [GestureDetector]
/// around [InteractiveViewer]: that arena fight breaks pinch (esp. figure-only).
/// Keep full-surface tap/double-tap; detect 1× figure swipe from pan-at-identity.
///
/// design/117 — figure advance only when the gesture stayed **one-finger**.
/// Pinch (incl. scale back to 1× while fingers down) must not change index.
///
/// design/118 — amplify pinch scale so the same finger travel feels stronger.
class _ZoomableFigureFrame extends StatefulWidget {
  const _ZoomableFigureFrame({
    super.key,
    required this.child,
    this.figureKey,
    this.annotations,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
    this.onTap,
    this.onDoubleTapExpand,
    this.onSwipeToSentence,
  });

  final Widget child;
  final String? figureKey;
  final AnnotationController? annotations;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTapExpand;
  /// design/156 — figure full-screen @ 1×: swipe down → sentence panel.
  final VoidCallback? onSwipeToSentence;

  @override
  State<_ZoomableFigureFrame> createState() => _ZoomableFigureFrameState();
}

class _ZoomableFigureFrameState extends State<_ZoomableFigureFrame>
    with TickerProviderStateMixin {
  final TransformationController _transform = TransformationController();
  static const double _minDistance = 56;
  static const double _minVerticalDistance = 88;
  static const double _minVelocity = 180;
  static const double _zoomEps = 1.02;
  static const double _maxScale = 8.0;
  Offset _panAtStart = Offset.zero;
  /// Peak [ScaleUpdateDetails.pointerCount] for the in-flight gesture.
  int _maxPointers = 0;
  /// Scale on axis at [onInteractionStart] — base for design/118 amplify.
  double _scaleAtGestureStart = 1.0;
  Offset _lastFocalPoint = Offset.zero;
  double _viewWidth = 1;
  /// design/448 — the frame size when the zoom began. Full screen and back moves
  /// far from it; a folding button row does not.
  Size? _zoomFrameSize;
  static const double _zoomFrameDrift = 1 / 3;
  Size _frameSize = Size.zero;
  double _fingerDx = 0;
  double _fingerDy = 0;
  AnimationController? _slide;
  int _slideGen = 0;
  /// design/459 — the figure flew off and waits for the next [figureKey].
  bool _parked = false;
  Timer? _parkTimer;
  /// design/471 — a plain wheel turns figures, so it must not zoom. Ctrl+wheel
  /// still zooms (it arrives as a scale event). The factor also brakes the
  /// pinch fling, so a touch screen keeps the stock one.
  bool _sawTouch = false;
  static const double _touchScaleFactor = 200;
  static const double _wheelNoZoom = 1e9;

  @override
  void didUpdateWidget(covariant _ZoomableFigureFrame oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_parked && widget.figureKey != oldWidget.figureKey) {
      _parkTimer?.cancel();
      _parked = false;
      _transform.value = Matrix4.identity();
    }
  }

  @override
  void dispose() {
    _parkTimer?.cancel();
    _slide?.dispose();
    _transform.dispose();
    super.dispose();
  }

  void _stopSlide() {
    _slideGen++;
    _slide?.dispose();
    _slide = null;
    _parkTimer?.cancel();
    _parked = false;
  }

  /// design/448 — a zoom kept across full screen and back points outside the
  /// smaller frame, and the figure is gone from it.
  void _resetZoom() {
    _stopSlide();
    _zoomFrameSize = null;
    if (_transform.value != Matrix4.identity()) {
      _transform.value = Matrix4.identity();
    }
  }

  void _onDoubleTap() {
    _resetZoom();
    widget.onDoubleTapExpand?.call();
  }

  void _noteFrameSize(Size size) {
    _frameSize = size;
    final from = _zoomFrameSize;
    if (from == null) return;
    bool far(double a, double b) => (a - b).abs() > _zoomFrameDrift * a;
    if (!far(from.width, size.width) && !far(from.height, size.height)) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _zoomFrameSize == from) _resetZoom();
    });
  }

  void _onInteractionStart(ScaleStartDetails details) {
    _stopSlide();
    // WHY: capture translation at gesture start for 1× horizontal swipe.
    final t = _transform.value.getTranslation();
    _panAtStart = Offset(t.x, t.y);
    _maxPointers = details.pointerCount;
    _scaleAtGestureStart = _transform.value.getMaxScaleOnAxis();
    _lastFocalPoint = details.localFocalPoint;
    _fingerDx = 0;
    _fingerDy = 0;
    _zoomFrameSize ??= _frameSize;
  }

  void _onInteractionUpdate(ScaleUpdateDetails details) {
    // WHY: pinch often starts as 1 pointer then becomes 2 — track the peak.
    if (details.pointerCount > _maxPointers) {
      _maxPointers = details.pointerCount;
    }
    final scaleNow = _transform.value.getMaxScaleOnAxis();
    // 1× horizontal swipe follows the finger with resistance. Zoomed pan stays put.
    if (widget.swipeEnabled &&
        details.pointerCount == 1 &&
        scaleNow <= _zoomEps) {
      _fingerDx += details.focalPointDelta.dx;
      _fingerDy += details.focalPointDelta.dy;
      if (_fingerDx.abs() + 8 >= _fingerDy.abs()) {
        final resisted = rubberBandOffset(_fingerDx, _viewWidth);
        _transform.value = Matrix4.identity()..setTranslationRaw(resisted, 0, 0);
        _lastFocalPoint = details.localFocalPoint;
        return;
      }
    }
    // design/118+156 — amplify zoomed one-finger pan (IV is 1:1 by default).
    if (details.pointerCount == 1 && scaleNow > _zoomEps) {
      final delta = details.localFocalPoint - _lastFocalPoint;
      _lastFocalPoint = details.localFocalPoint;
      final extraX = amplifyFigurePanExtraDelta(delta: delta.dx);
      final extraY = amplifyFigurePanExtraDelta(delta: delta.dy);
      if (extraX.abs() > 1e-4 || extraY.abs() > 1e-4) {
        _transform.value = Matrix4.copy(_transform.value)
          ..translate(extraX, extraY);
      }
      return;
    }
    _lastFocalPoint = details.localFocalPoint;
    // design/118 — InteractiveViewer already applied 1:1 scale; strengthen it.
    // One-finger pan must stay untouched (117 swipe path).
    if (details.pointerCount < 2) return;
    final amplified = amplifyFigurePinchScale(rawScale: details.scale);
    final target =
        (_scaleAtGestureStart * amplified).clamp(1.0, _maxScale).toDouble();
    final current = _transform.value.getMaxScaleOnAxis();
    // EDGE: degenerate matrix — do not divide / explode.
    if (!current.isFinite || current < 1e-6) return;
    final factor = target / current;
    if (!factor.isFinite || (factor - 1.0).abs() < 1e-4) return;
    // Scale about the focal point so the figure does not jump sideways.
    final focalScene = _transform.toScene(details.localFocalPoint);
    final next = Matrix4.copy(_transform.value)
      ..translate(focalScene.dx, focalScene.dy)
      ..scale(factor)
      ..translate(-focalScene.dx, -focalScene.dy);
    _transform.value = next;
  }

  void _onInteractionEnd(ScaleEndDetails details) {
    if (!mounted) return;
    final scale = _transform.value.getMaxScaleOnAxis();
    final t = _transform.value.getTranslation();
    final dx = t.x - _panAtStart.dx;
    final dy = t.y - _panAtStart.dy;
    final maxPointers = _maxPointers;
    final fingerDx = _fingerDx;
    final fingerDy = _fingerDy;
    // Reset for the next gesture (after fingers up, one-finger swipe works again).
    _maxPointers = 0;
    _fingerDx = 0;
    _fingerDy = 0;

    // EDGE: pinch ended above 1× — keep pan/zoom; no figure change.
    if (scale > _zoomEps) {
      return;
    }
    _zoomFrameSize = null;

    // design/156 — vertical panel swap (before 1× snap-back).
    if (widget.onSwipeToSentence != null && maxPointers < 2) {
      final goDown = dy > _minVerticalDistance ||
          details.velocity.pixelsPerSecond.dy > _minVelocity;
      if (dy.abs() > dx.abs() && fingerDy.abs() >= fingerDx.abs() && goDown) {
        _transform.value = Matrix4.identity();
        widget.onSwipeToSentence!();
        return;
      }
    }

    final v = details.velocity.pixelsPerSecond.dx;
    final horizontal = fingerDx.abs() >= fingerDy.abs();
    final goNext = fingerDx < -_minDistance || v < -_minVelocity;
    final goPrev = fingerDx > _minDistance || v > _minVelocity;
    if (horizontal &&
        widget.swipeEnabled &&
        allowFigureSwipeAfterPan(
          maxPointerCount: maxPointers,
          scale: scale,
          zoomEps: _zoomEps,
        ) &&
        ((goPrev && widget.onPrevious != null) ||
            (goNext && widget.onNext != null))) {
      final to = flingTarget(goPrev ? 1 : -1, _viewWidth);
      _flyFigure(to, () {
        if (goPrev && widget.onPrevious != null) {
          widget.onPrevious!();
        } else {
          widget.onNext?.call();
        }
      });
      return;
    }

    // Cancelled 1× drag springs back. A zoomed view never reaches here.
    if (horizontal && _transform.value.getTranslation().x.abs() > 0.5) {
      _springFigureBack(v);
      return;
    }

    // WHY: 1× pan was only for swipe affordance — snap matrix back so the
    // figure does not sit offset after a failed/short drag / pinch-out.
    final needsSnap = (t.x.abs() > 0.5 ||
        t.y.abs() > 0.5 ||
        (scale - 1.0).abs() > 0.001);
    if (needsSnap) {
      _transform.value = Matrix4.identity();
    }
  }

  void _flyFigure(double target, VoidCallback then) {
    _stopSlide();
    final gen = _slideGen;
    final from = _transform.value.getTranslation().x;
    final ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 220),
    );
    _slide = ctrl;
    final anim = Tween<double>(begin: from, end: target).animate(
      CurvedAnimation(parent: ctrl, curve: Curves.easeIn),
    );
    ctrl.addListener(() {
      if (!mounted || gen != _slideGen) return;
      _transform.value = Matrix4.identity()..setTranslationRaw(anim.value, 0, 0);
    });
    ctrl.forward().whenComplete(() {
      if (!mounted || gen != _slideGen) return;
      _parked = true;
      _parkTimer = Timer(kSwipeParkLimit, () {
        if (mounted && _parked) _springFigureBack(0);
      });
      then();
    });
  }

  void _springFigureBack(double velocity) {
    final from = _transform.value.getTranslation().x;
    if (from.abs() < 0.5 && velocity.abs() < 8) {
      _transform.value = Matrix4.identity();
      return;
    }
    _stopSlide();
    final gen = _slideGen;
    final sim = SpringSimulation(
      const SpringDescription(mass: 0.55, stiffness: 280, damping: 20),
      from,
      0,
      velocity,
    );
    final ctrl = AnimationController.unbounded(vsync: this);
    _slide = ctrl;
    ctrl.addListener(() {
      if (!mounted || gen != _slideGen) return;
      _transform.value = Matrix4.identity()..setTranslationRaw(ctrl.value, 0, 0);
    });
    ctrl.animateWith(sim).whenComplete(() {
      if (!mounted || gen != _slideGen) return;
      _transform.value = Matrix4.identity();
    });
  }

  @override
  Widget build(BuildContext context) {
    final annotations = widget.annotations;
    final inkMode = annotations?.figureInkMode ?? false;
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        if (!w.isFinite || !h.isFinite || w <= 0 || h <= 0) {
          return widget.child;
        }
        _viewWidth = w;
        _noteFrameSize(Size(w, h));
        final zoomChild = annotations != null
            ? _FigureInkOverlay(
                figureKey: widget.figureKey,
                annotations: annotations,
                child: widget.child,
              )
            : widget.child;
        // Pen/eraser take the finger. With neither armed, pan and zoom stay on.
        final inkDraws = figureInkCapturesPointer(
          inkMode: inkMode,
          tool: annotations?.figureInkTool,
        );
        return Listener(
          onPointerDown: (e) {
            if (e.kind == PointerDeviceKind.touch && !_sawTouch) {
              setState(() => _sawTouch = true);
            }
          },
          child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: inkMode ? null : widget.onTap,
          onDoubleTap: inkMode || widget.onDoubleTapExpand == null
              ? null
              : _onDoubleTap,
          child: InteractiveViewer(
            transformationController: _transform,
            minScale: 1.0,
            maxScale: _maxScale,
            panEnabled: !inkDraws,
            scaleEnabled: !inkDraws,
            scaleFactor: _sawTouch ? _touchScaleFactor : _wheelNoZoom,
            // A touchpad swipe turns figures too; as a pan it would wobble.
            trackpadScrollCausesScale: !_sawTouch,
            boundaryMargin: const EdgeInsets.all(48),
            onInteractionStart: inkDraws ? null : _onInteractionStart,
            onInteractionUpdate: inkDraws ? null : _onInteractionUpdate,
            onInteractionEnd: inkDraws ? null : _onInteractionEnd,
            child: SizedBox(
              width: w,
              height: h,
              child: ColoredBox(
                color: Colors.black,
                child: Center(child: zoomChild),
              ),
            ),
          ),
          ),
        );
      },
    );
  }
}

Future<void> _handleSentenceBookmarkTap(
  BuildContext context, {
  required BookmarkController bookmarks,
  required ReadingSession session,
}) async {
  if (!bookmarks.canBookmark) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('북마크를 쓰려면 로그인해 주세요.')),
    );
    return;
  }
  final nav = session.sectionNav;
  final key = nav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
  if (bookmarks.isSentenceBookmarked(key)) {
    await bookmarks.toggleSentenceBookmark(nav, session.sentenceIndex);
    return;
  }
  final header = nav.headerPartsFor(session.sentenceIndex);
  final label = header.sectionName.isEmpty
      ? '${header.position}번 문장'
      : '${header.sectionName} ${header.position}번';
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('북마크할까요?'),
      content: Text(
        '$label을 북마크하면 쉽게 찾을 수 있어요.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('아니오'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('예'),
        ),
      ],
    ),
  );
  if (ok == true) {
    await bookmarks.toggleSentenceBookmark(nav, session.sentenceIndex);
  }
}

Future<void> _handleSentenceAnnotateLongPress(
  BuildContext context, {
  required AnnotationController annotations,
  required ReadingSession session,
}) async {
  final nav = session.sectionNav;
  final key = nav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
  if (key == null) return;
  final cur = session.currentSentence;
  if (cur == null) return;
  final existing = annotations.activeForSentenceKey(key);
  final result = await showAnnotationToolbarSheet(
    context: context,
    existing: existing,
    canAnnotate: annotations.canAnnotate,
    sentencePlain: annotationPlainForSentence(cur.text),
  );
  if (result == null || !context.mounted) return;

  switch (result.action) {
    case AnnotationSheetAction.armPaint:
      if (!annotations.canAnnotate) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('주석을 쓰려면 로그인해 주세요.')),
        );
        return;
      }
      annotations.armSentencePaint(
        color: result.color,
        sentenceKey: key,
        sentenceIndex: session.sentenceIndex,
      );
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('단어를 문지르면 칠해집니다')),
      );
      return;
    case AnnotationSheetAction.deleteAll:
      if (!annotations.canAnnotate) return;
      await annotations.removeAnnotationsForKey(key);
      return;
    case AnnotationSheetAction.saveMeta:
      if (!annotations.canAnnotate) return;
      final id = result.existingId;
      if (id == null || id.isEmpty) return;
      await annotations.updateHighlightMeta(
        sentenceKey: key,
        existingId: id,
        color: result.color,
        note: result.note,
      );
      HapticFeedback.mediumImpact();
      return;
    case AnnotationSheetAction.askAi:
      await _askAiAbout(
        context,
        sentencePlain: annotationPlainForSentence(cur.text),
        promptBody: result.promptBody ?? '',
      );
      return;
  }
}

Future<void> _askAiAbout(
  BuildContext context, {
  required String sentencePlain,
  required String promptBody,
}) async {
  final body = promptBody.trim();
  if (body.isEmpty) return;
  final launch = await runAiAsk(sentencePlain: sentencePlain, promptBody: body);
  if (!context.mounted || launch.direct) return;
  if (!launch.copied) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('프롬프트가 비어 있습니다')),
    );
    return;
  }
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(
        launch.launched
            ? '복사됨 · Google AI에서 붙여넣기 하세요'
            : '복사는 됐습니다. 브라우저에서 google.com/ai를 열어 붙여넣기 하세요',
      ),
    ),
  );
}

Future<void> _askAiAboutFigure(
  BuildContext context, {
  required DecodedImageBytes image,
  required String question,
}) async {
  final launch = await runFigureAiAsk(
    image: image.bytes,
    mime: image.mime,
    question: question,
  );
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(
        !launch.copied
            ? '그림을 복사하지 못했어요'
            : launch.launched
                ? 'AI 창에서 Ctrl+V 로 그림을 넣어 주세요'
                : '복사는 됐어요. 브라우저에서 google.com/ai 를 열어 붙여넣어 주세요',
      ),
    ),
  );
}

Future<void> _handleFigureBookmarkTap(
  BuildContext context, {
  required BookmarkController bookmarks,
  required ReadingSession session,
}) async {
  if (!bookmarks.canBookmark) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('북마크를 쓰려면 로그인해 주세요.')),
    );
    return;
  }
  final nav = session.figureNav;
  final key = nav.figureBookmarkKeyForCarousel(session.figureIndex);
  if (bookmarks.isFigureBookmarked(key)) {
    await bookmarks.toggleFigureBookmark(nav, session.figureIndex);
    return;
  }
  final header = nav.headerPartsFor(
    session.figureIndex,
    totalFigures: session.figureCount,
  );
  final kind = header.kindLabel.isEmpty ? 'Figure' : header.kindLabel;
  final num = header.numberLabel.isEmpty ? '?' : header.numberLabel;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('북마크할까요?'),
      content: Text(
        '$kind $num을 북마크하면 쉽게 찾을 수 있어요.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('아니오'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('예'),
        ),
      ],
    ),
  );
  if (ok == true) {
    await bookmarks.toggleFigureBookmark(nav, session.figureIndex);
  }
}
