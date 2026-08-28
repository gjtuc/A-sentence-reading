/// design/151 — slot carousel overlay editor (tap O/X assign body/caption).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../widgets/layout_overlay.dart';

class FigureEditScreen extends StatefulWidget {
  const FigureEditScreen({
    super.key,
    required this.client,
    required this.cacheId,
  });

  final AsrClient client;
  final String cacheId;

  @override
  State<FigureEditScreen> createState() => _FigureEditScreenState();
}

class _FigureEditScreenState extends State<FigureEditScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _slots = [];
  List<LayoutBoxView> _boxes = [];
  int _pageIndex = 0;
  String? _selectedSlotKey;
  _PickMode _pickMode = _PickMode.none;
  String _status = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final layout = await widget.client.fetchLayoutMap(widget.cacheId);
      final plan = await widget.client.fetchSlotPlan(widget.cacheId);
      final pages = (layout['pages'] as List?) ?? [];
      final pageMeta = _pageIndex < pages.length && pages[_pageIndex] is Map
          ? pages[_pageIndex] as Map<String, dynamic>
          : <String, dynamic>{'width_pt': 612, 'height_pt': 792};
      final pw = (pageMeta['width_pt'] as num?)?.toInt() ?? 612;
      final ph = (pageMeta['height_pt'] as num?)?.toInt() ?? 792;
      final rawBoxes = (layout['boxes'] as List?) ?? [];
      final boxes = rawBoxes
          .whereType<Map>()
          .map(
            (b) => LayoutBoxView.fromJson(
              Map<String, dynamic>.from(b),
              pageW: pw,
              pageH: ph,
            ),
          )
          .toList();
      final slots = (plan['slots'] as List?) ?? [];
      if (!mounted) return;
      setState(() {
        _boxes = boxes;
        _slots = slots
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
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

  void _selectSlot(String key) {
    setState(() {
      _selectedSlotKey = key;
      _pickMode = _PickMode.body;
      _status = 'Select figure/table body';
    });
  }

  Future<void> _onBoxTap(LayoutBoxView box) async {
    if (_selectedSlotKey == null || _pickMode == _PickMode.none) return;
    final preview = box.text.trim().isNotEmpty
        ? box.text.trim()
        : '${box.kind} ${box.id}';
    final ok = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => _ConfirmSheet(label: preview),
    );
    if (ok != true || !mounted) return;
    final slotKey = _selectedSlotKey!;
    try {
      if (_pickMode == _PickMode.body) {
        await widget.client.assignSlot(
          widget.cacheId,
          slotKey,
          bodyBoxId: box.id,
        );
        setState(() {
          _pickMode = _PickMode.caption;
          _status = 'Select caption (optional)';
        });
      } else {
        await widget.client.assignSlot(
          widget.cacheId,
          slotKey,
          captionBoxId: box.id,
          captionText: box.text,
        );
        await widget.client.renderSlot(widget.cacheId, slotKey);
        if (!mounted) return;
        setState(() {
          _pickMode = _PickMode.none;
          _status = 'Saved $slotKey';
        });
        await _load();
      }
    } on AsrApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Figure layout edit'),
        actions: [
          IconButton(
            tooltip: 'prev page',
            onPressed: _pageIndex > 0
                ? () => setState(() => _pageIndex -= 1)
                : null,
            icon: const Icon(Icons.chevron_left),
          ),
          Text('p.${_pageIndex + 1}'),
          IconButton(
            tooltip: 'next page',
            onPressed: () => setState(() => _pageIndex += 1),
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
                    if (_status.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.all(8),
                        child: Text(_status, textAlign: TextAlign.center),
                      ),
                    SizedBox(
                      height: 120,
                      child: ListView.builder(
                        scrollDirection: Axis.horizontal,
                        itemCount: _slots.length,
                        itemBuilder: (ctx, i) {
                          final s = _slots[i];
                          final key = '${s['key'] ?? ''}';
                          final status = '${s['status'] ?? ''}';
                          final selected = key == _selectedSlotKey;
                          return Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 4),
                            child: ChoiceChip(
                              label: Text('$key ($status)'),
                              selected: selected,
                              onSelected: (_) => _selectSlot(key),
                            ),
                          );
                        },
                      ),
                    ),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: LayoutOverlay(
                          boxes: _boxes,
                          pageIndex: _pageIndex,
                          onBoxTap: _onBoxTap,
                          child: ColoredBox(
                            color: Colors.grey.shade200,
                            child: Center(
                              child: Text(
                                'PDF page ${_pageIndex + 1}\n(tap colored box)',
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }
}

enum _PickMode { none, body, caption }

class _ConfirmSheet extends StatelessWidget {
  const _ConfirmSheet({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(label, maxLines: 4, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('✕ Cancel'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    onPressed: () => Navigator.pop(context, true),
                    child: const Text('✓ Insert'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
