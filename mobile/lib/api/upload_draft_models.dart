/// Pending upload / reanalyze draft for resume (design/71 · 72 · 168f H1.5).
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
    this.cacheId = '',
    this.purpose = 'upload',
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

  /// design/168f — reanalyze target cache (empty for normal upload).
  final String cacheId;

  /// `upload` | `reanalyze`
  final String purpose;

  bool get hasJob => jobId.trim().isNotEmpty;
  bool get hasUpload => uploadId.trim().isNotEmpty;
  bool get canReattach => hasJob && phase == 'processing';
  bool get canResumeChunks =>
      purpose != 'reanalyze' && hasUpload && phase == 'uploading';
  bool get isReanalyze => purpose == 'reanalyze';

  Map<String, dynamic> toJson() => {
        'content_hash': contentHash,
        'filename': filename,
        'job_id': jobId,
        'upload_id': uploadId,
        'phase': phase,
        'local_path': localPath,
        'bytes_len': bytesLen,
        'cache_id': cacheId,
        'purpose': purpose,
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
    final cid = '${m['cache_id'] ?? ''}'.trim();
    if (cid.isNotEmpty && !RegExp(r'^[a-zA-Z0-9]{8,32}$').hasMatch(cid)) {
      return null;
    }
    var purpose = '${m['purpose'] ?? 'upload'}'.trim();
    if (purpose != 'upload' && purpose != 'reanalyze') {
      purpose = 'upload';
    }
    if (purpose == 'reanalyze' && cid.isEmpty) {
      return null;
    }
    return UploadDraft(
      contentHash: hash,
      filename: name,
      jobId: job,
      uploadId: upl,
      phase: phase,
      localPath: '${m['local_path'] ?? ''}'.trim(),
      bytesLen: len < 0 ? 0 : len,
      cacheId: cid,
      purpose: purpose,
    );
  }

  String encode() => jsonEncode(toJson());

  UploadDraft copyWith({
    String? jobId,
    String? uploadId,
    String? phase,
    String? localPath,
    String? cacheId,
    String? purpose,
  }) {
    return UploadDraft(
      contentHash: contentHash,
      filename: filename,
      jobId: jobId ?? this.jobId,
      uploadId: uploadId ?? this.uploadId,
      phase: phase ?? this.phase,
      localPath: localPath ?? this.localPath,
      bytesLen: bytesLen,
      cacheId: cacheId ?? this.cacheId,
      purpose: purpose ?? this.purpose,
    );
  }
}
