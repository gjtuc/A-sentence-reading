import '../api/upload_limits.dart';

/// design/458 · 460 — which dropped files go to the upload queue.
bool droppableDoc(String name, int size, {int maxBytes = kMaxUploadBytes}) {
  final n = name.trim().toLowerCase();
  return (n.endsWith('.pdf') || n.endsWith('.docx')) && size > 0 && size <= maxBytes;
}
