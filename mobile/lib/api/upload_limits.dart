/// design/460 — one size cap for a paper file: upload, folder read, head read,
/// drop. The server checks the same number (`_MAX_UPLOAD_BYTES`).
library;

const int kMaxUploadBytes = 100 * 1024 * 1024;
