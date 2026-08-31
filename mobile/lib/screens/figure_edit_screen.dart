/// design/151/163 — slot overlay editor with PDF background, union multi-select.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../services/figure_edit_compositor.dart';
import '../services/figure_edit_geometry.dart';
import '../services/figure_edit_session.dart';
import '../services/paper_edit_stash.dart';
import '../services/paper_edit_stash_service.dart';
import '../widgets/layout_overlay.dart';

enum _EditMode { pan, select, crop }

class FigureEditScreen extends StatefulWidget {
  const FigureEditScreen({
    super.key,
    required this.client,
    required this.cacheId,
    this.hasSource = false,
    this.contentHash = '',
    this.editStash,
  });

  final AsrClient client;
  final String cacheId;
  final bool hasSource;
  final String contentHash;
  final PaperEditStash? editStash;

  @override
  State<FigureEditScreen> createState() => _FigureEditScreenState();
}

class _FigureEditScreenState extends State<FigureEditScreen> {
  late final PaperEditStash _stash = widget.editStash ?? PaperEditStash();

  bool _loading = true;
  bool _saving = false;
  String? _error;
  FigureEditSession? _session;
  List<LayoutBoxView> _boxes = [];
  int _pageIndex = 0;
  String? _selectedSlotKey;
  _EditMode _mode = _EditMode.select;
  String _status = '';
  Uint8List? _pagePng;
  double _pageAspect = 612 / 792;
  final Set<String> _selectedBoxIds = {};
  final Map<int, Uint8List> _pagePngCache = {};
  Offset? _dragStart;
  Offset? _dragEnd;
  final TransformationController _transform = TransformationController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  Future<Uint8List?> _pagePngFor(int pageIndex) async {
    if (_pagePngCache.containsKey(pageIndex)) {
      return _pagePngCache[pageIndex];
    }
    if (!widget.hasSource) return null;
    final png = await ensurePagePreview(
      client: widget.client,
      stash: _stash,
      cacheId: widget.cacheId,
      pageIndex: pageIndex,
    );
    _pagePngCache[pageIndex] = png;
    return png;
  }

  List<LayoutBoxView> _buildBoxViews(Map<String, dynamic> layout, int pageIndex) {
    final pages = (layout['pages'] as List?) ?? [];
    final pageMeta = pageIndex < pages.length && pages[pageIndex] is Map
        ? pages[pageIndex] as Map<String, dynamic>
        : <String, dynamic>{'width_pt': 612, 'height_pt': 792};
    final pw = (pageMeta['width_pt'] as num?)?.toInt() ?? 612;
    final ph = (pageMeta['height_pt'] as num?)?.toInt() ?? 792;
    final rawBoxes = (layout['boxes'] as List?) ?? [];
    return rawBoxes
        .whereType<Map>()
        .map(
          (b) => LayoutBoxView.fromJson(
            Map<String, dynamic>.from(b),
            pageW: pw,
            pageH: ph,
          ),
        )
        .toList();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (widget.hasSource) {
        await ensurePaperEditStash(
          client: widget.client,
          stash: _stash,
          cacheId: widget.cacheId,
          hasSource: widget.hasSource,
          contentHash: widget.contentHash,
        );
      }
      final layout = await widget.client.fetchLayoutMap(widget.cacheId);
      final plan = await widget.client.fetchSlotPlan(widget.cacheId);
      final slots = (plan['slots'] as List?) ?? [];
      final session = FigureEditSession(
        cacheId: widget.cacheId,
        layoutMap: layout,
        slots: slots.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList(),
      );
      final boxes = _buildBoxViews(session.layoutMap, _pageIndex);
      final png = widget.hasSource ? await _pagePngFor(_pageIndex) : null;
      final pw = session.pageWidth(_pageIndex);
      final ph = session.pageHeight(_pageIndex);
      if (!mounted) return;
      setState(() {
        _session = session;
        _boxes = boxes;
        _pagePng = png;
        _pageAspect = pw / ph;
        _loading = false;
      });
    } on PaperStashException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message.isNotEmpty ? e.message : '원본이 없습니다.';
        _loading = false;
      });
    } on AsrApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  Future<void> _changePage(int delta) async {
    final next = _pageIndex + delta;
    if (next < 0) return;
    setState(() {
      _pageIndex = next;
      _pagePng = null;
      _selectedBoxIds.clear();
      _dragStart = null;
      _dragEnd = null;
    });
    final session = _session;
    if (session == null) return;
    final png = widget.hasSource ? await _pagePngFor(next) : null;
    if (!mounted) return;
    setState(() {
      _boxes = _buildBoxViews(session.layoutMap, next);
      _pagePng = png;
      _pageAspect = session.pageWidth(next) / session.pageHeight(next);
    });
  }

  void _selectSlot(String key) {
    setState(() {
      _selectedSlotKey = key;
      _selectedBoxIds.clear();
      _status = 'Select boxes → Add body/caption';
    });
  }

  void _onBoxTap(LayoutBoxView box) {
    if (_mode != _EditMode.select) return;
    setState(() {
      if (_selectedBoxIds.contains(box.id)) {
        _selectedBoxIds.remove(box.id);
      } else {
        _selectedBoxIds.add(box.id);
      }
    });
  }

  List<LayoutBoxView> _selectedBoxes() {
    return _boxes.where((b) => _selectedBoxIds.contains(b.id)).toList();
  }

  Future<void> _assignSelection({required bool caption}) async {
    final session = _session;
    final slotKey = _selectedSlotKey;
    if (session == null || slotKey == null) return;
    final selected = _selectedBoxes();
    if (selected.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('박스를 선택하세요.')),
      );
      return;
    }
    if (!samePage(selected)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('같은 페이지의 박스만 선택할 수 있습니다.')),
      );
      return;
    }
    final union = unionBoxes(selected);
    final slot = session.slotByKey(slotKey);
    if (slot == null) return;
    final pagePng = await _pagePngFor(selected.first.pageIndex);
    setState(() {
      if (caption) {
        slot.captionBoxIds = selected.map((b) => b.id).toList();
        slot.captionUnion = union;
      } else {
        slot.bodyBoxIds = selected.map((b) => b.id).toList();
        slot.bodyUnion = union;
      }
      slot.status = 'user_confirmed';
      session.dirty = true;
      if (pagePng != null) {
        slot.previewPng = composeSlotPng(
          bodyPagePng: pagePng,
          bodyRect: slot.bodyUnion,
          captionPagePng: pagePng,
          captionRect: slot.captionUnion,
          isTable: slot.isTable,
        );
      }
      _selectedBoxIds.clear();
      _status = caption ? 'Caption set for $slotKey' : 'Body set for $slotKey';
    });
  }

  void _onPanStart(DragStartDetails d, Size size) {
    if (_mode != _EditMode.crop) return;
    setState(() {
      _dragStart = d.localPosition;
      _dragEnd = d.localPosition;
    });
  }

  void _onPanUpdate(DragUpdateDetails d) {
    if (_mode != _EditMode.crop || _dragStart == null) return;
    setState(() => _dragEnd = d.localPosition);
  }

  void _onPanEnd(DragEndDetails d, Size size) {
    final session = _session;
    if (_mode != _EditMode.crop || session == null || _dragStart == null || _dragEnd == null) {
      return;
    }
    final rect = normRectFromDrag(
      start: _dragStart!,
      end: _dragEnd!,
      size: size,
    );
    if (!rect.isValid || (rect.right - rect.left) < 0.02 || (rect.bottom - rect.top) < 0.02) {
      setState(() {
        _dragStart = null;
        _dragEnd = null;
      });
      return;
    }
    session.addManualBox(pageIndex: _pageIndex, rect: rect);
    setState(() {
      _boxes = _buildBoxViews(session.layoutMap, _pageIndex);
      _dragStart = null;
      _dragEnd = null;
      _status = 'Manual crop added';
    });
  }

  Future<bool> _commitIfDirty() async {
    final session = _session;
    if (session == null || !session.dirty) return true;
    setState(() => _saving = true);
    try {
      final figures = <({
        String slotKey,
        String caption,
        int? pageIndex,
        Uint8List png,
      })>[];
      for (final slot in session.slotStates) {
        if (slot.previewPng == null || slot.previewPng!.isEmpty) continue;
        figures.add((
          slotKey: slot.key,
          caption: slot.captionText,
          pageIndex: _pageIndex,
          png: slot.previewPng!,
        ));
      }
      if (figures.isEmpty) {
        return true;
      }
      await widget.client.commitFigureEdit(
        cacheId: widget.cacheId,
        layoutMap: session.layoutMap,
        slotPlan: session.slotPlanJson(),
        figures: figures,
      );
      session.dirty = false;
      return true;
    } on AsrApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
      return false;
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _onWillPop() async {
    final session = _session;
    if (session == null || !session.dirty) {
      if (mounted) Navigator.of(context).pop();
      return;
    }
    final save = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Save changes?'),
        content: const Text('저장하고 나가면 서버에 반영됩니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Discard'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (save == true) {
      final ok = await _commitIfDirty();
      if (ok && mounted) Navigator.of(context).pop();
    } else if (save == false && mounted) {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = _session;
    final slot = _selectedSlotKey != null && session != null
        ? session.slotByKey(_selectedSlotKey!)
        : null;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _onWillPop();
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Figure layout edit'),
          actions: [
            if (session?.dirty == true)
              TextButton(
                onPressed: _saving ? null : () async {
                  final ok = await _commitIfDirty();
                  if (ok && mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Saved')),
                    );
                  }
                },
                child: _saving
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Save'),
              ),
            IconButton(
              tooltip: 'prev page',
              onPressed: _pageIndex > 0 && !_loading
                  ? () => _changePage(-1)
                  : null,
              icon: const Icon(Icons.chevron_left),
            ),
            Text('p.${_pageIndex + 1}'),
            IconButton(
              tooltip: 'next page',
              onPressed: !_loading ? () => _changePage(1) : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!))
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        child: SegmentedButton<_EditMode>(
                          segments: const [
                            ButtonSegment(
                              value: _EditMode.pan,
                              label: Text('Pan'),
                              icon: Icon(Icons.pan_tool_alt_outlined),
                            ),
                            ButtonSegment(
                              value: _EditMode.select,
                              label: Text('Select'),
                              icon: Icon(Icons.touch_app_outlined),
                            ),
                            ButtonSegment(
                              value: _EditMode.crop,
                              label: Text('Crop'),
                              icon: Icon(Icons.crop_outlined),
                            ),
                          ],
                          selected: {_mode},
                          onSelectionChanged: (s) {
                            setState(() {
                              _mode = s.first;
                              _dragStart = null;
                              _dragEnd = null;
                            });
                          },
                        ),
                      ),
                      if (_status.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.all(8),
                          child: Text(_status, textAlign: TextAlign.center),
                        ),
                      SizedBox(
                        height: 100,
                        child: ListView.builder(
                          scrollDirection: Axis.horizontal,
                          itemCount: session?.slotStates.length ?? 0,
                          itemBuilder: (ctx, i) {
                            final s = session!.slotStates[i];
                            final selected = s.key == _selectedSlotKey;
                            return Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 4),
                              child: ChoiceChip(
                                label: Text('${s.key} (${s.status})'),
                                selected: selected,
                                onSelected: (_) => _selectSlot(s.key),
                              ),
                            );
                          },
                        ),
                      ),
                      if (slot?.previewPng != null)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          child: SizedBox(
                            height: 64,
                            child: Image.memory(slot!.previewPng!, fit: BoxFit.contain),
                          ),
                        ),
                      if (_selectedSlotKey != null)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          child: Row(
                            children: [
                              Expanded(
                                child: OutlinedButton(
                                  onPressed: () => _assignSelection(caption: false),
                                  child: const Text('본문에 추가'),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: OutlinedButton(
                                  onPressed: () => _assignSelection(caption: true),
                                  child: const Text('캡션에 추가'),
                                ),
                              ),
                              IconButton(
                                tooltip: 'Clear selection',
                                onPressed: () => setState(_selectedBoxIds.clear),
                                icon: const Icon(Icons.deselect),
                              ),
                            ],
                          ),
                        ),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.all(8),
                          child: LayoutBuilder(
                            builder: (context, constraints) {
                              final viewSize = Size(
                                constraints.maxWidth,
                                constraints.maxHeight,
                              );
                              final pageChild = LayoutOverlay(
                                boxes: _boxes,
                                pageIndex: _pageIndex,
                                selectedIds: _selectedBoxIds,
                                onBoxTap: _mode == _EditMode.select ? _onBoxTap : null,
                                child: _pagePng != null
                                    ? AspectRatio(
                                        aspectRatio: _pageAspect,
                                        child: Image.memory(
                                          _pagePng!,
                                          fit: BoxFit.contain,
                                          gaplessPlayback: true,
                                        ),
                                      )
                                    : ColoredBox(
                                        color: Colors.grey.shade200,
                                        child: Center(
                                          child: Text(
                                            'PDF page ${_pageIndex + 1}',
                                            textAlign: TextAlign.center,
                                          ),
                                        ),
                                      ),
                              );
                              Widget stack = Stack(
                                fit: StackFit.expand,
                                children: [
                                  pageChild,
                                  if (_dragStart != null && _dragEnd != null)
                                    Positioned.fromRect(
                                      rect: Rect.fromPoints(_dragStart!, _dragEnd!),
                                      child: IgnorePointer(
                                        child: DecoratedBox(
                                          decoration: BoxDecoration(
                                            border: Border.all(
                                              color: Colors.red,
                                              width: 2,
                                            ),
                                            color: Colors.red.withValues(alpha: 0.15),
                                          ),
                                        ),
                                      ),
                                    ),
                                ],
                              );
                              if (_mode == _EditMode.crop) {
                                stack = GestureDetector(
                                  onPanStart: (d) => _onPanStart(d, viewSize),
                                  onPanUpdate: _onPanUpdate,
                                  onPanEnd: (d) => _onPanEnd(d, viewSize),
                                  child: stack,
                                );
                              }
                              return InteractiveViewer(
                                transformationController: _transform,
                                panEnabled: _mode == _EditMode.pan,
                                scaleEnabled: _mode == _EditMode.pan,
                                minScale: 1,
                                maxScale: 4,
                                child: stack,
                              );
                            },
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }
}
