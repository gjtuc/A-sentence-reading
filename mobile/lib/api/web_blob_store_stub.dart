import 'dart:typed_data';

/// No browser store off the web.
Future<bool> webBlobPut(String key, List<int> bytes) async => false;

Future<Uint8List?> webBlobGet(String key) async => null;

Future<void> webBlobDelete(String key) async {}
