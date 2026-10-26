import '../api/upload_limits.dart';

/// design/458 · 460 — which dropped files go to the upload queue.
bool droppableDoc(String name, int size, {int maxBytes = kMaxUploadBytes}) {
  final n = name.trim().toLowerCase();
  return (n.endsWith('.pdf') || n.endsWith('.docx')) && size > 0 && size <= maxBytes;
}

/// design/461 — Word 97-2003 (.doc). Not read anywhere; the reader is told to
/// save it as .docx.
bool isOldWordDoc(String name) => name.trim().toLowerCase().endsWith('.doc');
