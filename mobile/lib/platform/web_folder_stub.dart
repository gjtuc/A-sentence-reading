import 'dart:typed_data';

import 'saf_tree_channel.dart';

/// No browser folder access off the web.
bool get webFolderSupported => false;

Future<SafTreePickResult?> webPickFolder({String? previous, bool downloads = false}) async => null;

Future<SafTreeListResult> webListPdfs(String treeUri, {int maxItems = 500}) async =>
    const SafTreeListResult(items: [], truncated: false);

Future<Uint8List?> webReadFile(String docUri, {int maxBytes = 50 * 1024 * 1024}) async => null;

Future<String?> webSha256(String docUri) async => null;

Future<bool> webForgetFolder(String treeUri) async => false;
