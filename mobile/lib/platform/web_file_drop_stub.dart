import 'dart:typed_data';

import '../api/upload_limits.dart';

typedef DroppedFile = ({String name, Uint8List bytes});

/// No file drops off the web.
void Function() installFileDrop({
  required void Function(bool over) onOver,
  required void Function(List<DroppedFile> files, int skipped) onFiles,
  int maxBytes = kMaxUploadBytes,
}) =>
    () {};
