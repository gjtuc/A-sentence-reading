/// design/458 — which dropped files go to the upload queue.
bool droppablePdf(String name, int size, {int maxBytes = 50 * 1024 * 1024}) =>
    name.trim().toLowerCase().endsWith('.pdf') && size > 0 && size <= maxBytes;
