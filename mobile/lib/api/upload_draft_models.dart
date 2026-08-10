/// Pending upload draft for resume (design/71 · design/72).
library;

import 'dart:convert';

const String kUploadDraftPrefsKey = 'asr.upload_draft.v1';

/// Local + job/chunk reattach state. Never stores session cookies or secrets.
class UploadDraft {
  UploadDraft({
    required this.contentHash,
    required this.filename,
    this.jobId = '',
    this.uploadId = '',
    this.phase = 'uploading',
    this.localPath = '',
    this.bytesLen = 0,
  });

  final String contentHash;
  final String filename;
  final String jobId;

  /// Chunked upload session (`upl_…`) while bytes are still transferring.
  final String uploadId;

  /// `uploading` = chunks in flight; `processing` = have job_id to poll.
  final String phase;
  final String localPath;
  final int bytesLen;

  bool get hasJob => jobId.trim().isNotEmpty;
  bool get hasUpload => uploadId.trim().isNotEmpty;
  bool get canReattach => hasJob && phase == 'processing';
  bool get canResumeChunks => hasUpload && phase == 'uploading';

  Map<String, dynamic> toJson() => {
        'content_hash': contentHash,
        'filename': filename,
        'job_id': jobId,
        'upload_id': uploadId,
        'phase': phase,
        'local_path': localPath,
        'bytes_len': bytesLen,
      };

  static UploadDraft? tryParse(String? raw) {
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      return fromJson(Map<String, dynamic>.from(decoded));
    } catch (_) {
      return null;
    }
  }

  static UploadDraft? fromJson(Map<String, dynamic> m) {
    final hash = '${m['content_hash'] ?? ''}'.trim().toLowerCase();
    final name = '${m['filename'] ?? ''}'.trim();
    // EDGE: refuse incomplete drafts — never invent a resume target.
    if (hash.length != 64 || name.isEmpty) return null;
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hash)) return null;
    final job = '${m['job_id'] ?? ''}'.trim();
    if (job.isNotEmpty && !RegExp(r'^job_[a-f0-9]{12}$').hasMatch(job)) {
      return null;
    }
    final upl = '${m['upload_id'] ?? ''}'.trim();
    if (upl.isNotEmpty && !RegExp(r'^upl_[a-f0-9]{12}$').hasMatch(upl)) {
      return null;
    }
    final phase = '${m['phase'] ?? 'uploading'}'.trim();
    if (phase != 'uploading' && phase != 'processing') return null;
    final len = m['bytes_len'] is num ? (m['bytes_len'] as num).toInt() : 0;
    return UploadDraft(
      contentHash: hash,
      filename: name,
      jobId: job,
      uploadId: upl,
      phase: phase,
      localPath: '${m['local_path'] ?? ''}'.trim(),
      bytesLen: len < 0 ? 0 : len,
    );
  }

  String encode() => jsonEncode(toJson());

  UploadDraft copyWith({
    String? jobId,
    String? uploadId,
    String? phase,
    String? localPath,
  }) {
    return UploadDraft(
      contentHash: contentHash,
      filename: filename,
      jobId: jobId ?? this.jobId,
      uploadId: uploadId ?? this.uploadId,
      phase: phase ?? this.phase,
      localPath: localPath ?? this.localPath,
      bytesLen: bytesLen,
    );
  }
}
