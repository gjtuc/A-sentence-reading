/// design/264 — Dart API for Documents/문장읽기 MES mirror.
library;

import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

const MethodChannel kDocumentsMirrorChannel =
    MethodChannel('asr/documents_mirror');

class DocumentsMirrorChannel {
  DocumentsMirrorChannel({MethodChannel? channel})
      : _channel = channel ?? kDocumentsMirrorChannel;

  final MethodChannel _channel;

  Future<bool> hasManagePermission() async {
    if (kIsWeb) return false;
    try {
      final v = await _channel.invokeMethod<dynamic>('hasManagePermission');
      return v == true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> requestManagePermission() async {
    if (kIsWeb) return false;
    try {
      final v = await _channel.invokeMethod<dynamic>('requestManagePermission');
      return v == true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> ensureUidRoot(String uid) async {
    if (kIsWeb) return false;
    try {
      final v = await _channel.invokeMethod<dynamic>('ensureUidRoot', {
        'uid': uid.trim(),
      });
      return v is Map && v['ok'] == true;
    } on PlatformException {
      return false;
    } catch (_) {
      return false;
    }
  }

  Future<bool> uidRootExists(String uid) async {
    if (kIsWeb) return false;
    try {
      final v = await _channel.invokeMethod<dynamic>('uidRootExists', {
        'uid': uid.trim(),
      });
      return v == true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> writeBytes({
    required String uid,
    required String relativePath,
    required Uint8List bytes,
  }) async {
    if (kIsWeb) return false;
    try {
      final v = await _channel.invokeMethod<dynamic>('writeBytes', {
        'uid': uid.trim(),
        'relativePath': relativePath.trim(),
        'bytes': bytes,
      });
      return v == true;
    } catch (_) {
      return false;
    }
  }

  Future<Uint8List?> readBytes({
    required String uid,
    required String relativePath,
  }) async {
    if (kIsWeb) return null;
    try {
      final v = await _channel.invokeMethod<dynamic>('readBytes', {
        'uid': uid.trim(),
        'relativePath': relativePath.trim(),
      });
      if (v is Uint8List) return v;
      if (v is List<int>) return Uint8List.fromList(v);
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<bool> deletePath({
    required String uid,
    required String relativePath,
  }) async {
    if (kIsWeb) return false;
    try {
      final v = await _channel.invokeMethod<dynamic>('deletePath', {
        'uid': uid.trim(),
        'relativePath': relativePath.trim(),
      });
      return v == true;
    } catch (_) {
      return false;
    }
  }

  Future<List<String>> listRelative({
    required String uid,
    String relativePath = '',
  }) async {
    if (kIsWeb) return const [];
    try {
      final v = await _channel.invokeMethod<dynamic>('listRelative', {
        'uid': uid.trim(),
        'relativePath': relativePath.trim(),
      });
      if (v is! List) return const [];
      return [
        for (final e in v)
          if ('$e'.trim().isNotEmpty) '$e'.trim(),
      ];
    } catch (_) {
      return const [];
    }
  }
}
