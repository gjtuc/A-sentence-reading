/// design/162 — live front-camera self-view for shadowing practice (no record/save).
library;

import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

/// Front-camera preview only. Disposed when removed from tree.
class PracticeMirrorPanel extends StatefulWidget {
  const PracticeMirrorPanel({super.key});

  @override
  State<PracticeMirrorPanel> createState() => _PracticeMirrorPanelState();
}

class _PracticeMirrorPanelState extends State<PracticeMirrorPanel>
    with WidgetsBindingObserver {
  CameraController? _controller;
  String? _error;
  bool _initializing = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_initCamera());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_disposeCamera());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      unawaited(_disposeCamera());
    } else if (state == AppLifecycleState.resumed) {
      unawaited(_initCamera());
    }
  }

  Future<void> _disposeCamera() async {
    final c = _controller;
    _controller = null;
    if (c != null) {
      await c.dispose();
    }
  }

  Future<void> _initCamera() async {
    if (_controller != null && _controller!.value.isInitialized) return;
    if (!mounted) return;
    setState(() {
      _initializing = true;
      _error = null;
    });
    try {
      await _disposeCamera();
      final cameras = await availableCameras();
      if (!mounted) return;
      if (cameras.isEmpty) {
        setState(() {
          _error = '카메라를 찾지 못했습니다.';
          _initializing = false;
        });
        return;
      }
      CameraDescription selected = cameras.first;
      for (final c in cameras) {
        if (c.lensDirection == CameraLensDirection.front) {
          selected = c;
          break;
        }
      }
      final controller = CameraController(
        selected,
        ResolutionPreset.medium,
        enableAudio: false,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _initializing = false;
        _error = null;
      });
    } on CameraException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.code == 'CameraAccessDenied'
            ? '카메라 권한이 없습니다.'
            : '카메라를 시작하지 못했습니다.';
        _initializing = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = '카메라를 시작하지 못했습니다.';
        _initializing = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    if (_error != null) {
      return Center(
        child: Text(
          _error!,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }
    if (_initializing || controller == null || !controller.value.isInitialized) {
      return const Center(child: CircularProgressIndicator());
    }
    // WHY: parent is a fixed short-wide box; AspectRatio+stretch squashed the
    // sensor image. Cover + clip keeps natural aspect (crop edges only).
    final preview = controller.value.previewSize;
    final previewW = preview?.height ?? 3.0;
    final previewH = preview?.width ?? 4.0;
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: SizedBox.expand(
        child: FittedBox(
          fit: BoxFit.cover,
          clipBehavior: Clip.hardEdge,
          child: SizedBox(
            width: previewW,
            height: previewH,
            child: Transform.flip(
              flipX: true,
              child: CameraPreview(controller),
            ),
          ),
        ),
      ),
    );
  }
}
