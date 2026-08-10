package com.gjtuc.sentence_reading

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.io.File
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/**
 * design/76 — resume chunk upload + job poll when the Flutter process is dead/frozen.
 *
 * Reads Flutter SharedPreferences draft + session (no secrets in Work input).
 * Fail-closed: missing session/draft → success(noop) without fake complete notify.
 */
class UploadResumeWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        return try {
            runResume()
        } catch (e: Exception) {
            Log.w(TAG, "resume failed: ${e.javaClass.simpleName}")
            try {
                UploadForegroundService.update(
                    applicationContext,
                    "업로드 중단됨",
                    "앱을 열면 이어갈 수 있습니다",
                    null,
                )
            } catch (_: Exception) {
            }
            Result.retry()
        }
    }

    private suspend fun runResume(): Result {
        val prefs = applicationContext.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE)
        val session = prefs.getString(KEY_SESSION, null)?.trim().orEmpty()
        val draftRaw = prefs.getString(KEY_DRAFT, null)?.trim().orEmpty()
        if (session.isEmpty() || draftRaw.isEmpty()) {
            // EDGE: nothing to resume — not a user-visible failure.
            return Result.success()
        }
        val draft = JSONObject(draftRaw)
        val phase = draft.optString("phase", "")
        val uploadId = draft.optString("upload_id", "").trim()
        val jobId = draft.optString("job_id", "").trim()
        val localPath = draft.optString("local_path", "").trim()
        val contentHash = draft.optString("content_hash", "").trim().lowercase()
        val filename = draft.optString("filename", "paper.pdf").trim().ifEmpty { "paper.pdf" }
        val bytesLen = draft.optLong("bytes_len", 0L)

        setForeground(buildForegroundInfo("PDF 올리는 중", "백그라운드에서 이어올리는 중"))

        var activeJobId = jobId
        if (phase == "uploading" || (activeJobId.isEmpty() && uploadId.isNotEmpty())) {
            if (uploadId.isEmpty() || localPath.isEmpty() || !localPath.contains("ingest_drafts")) {
                return Result.failure()
            }
            val file = File(localPath)
            if (!file.isFile || !file.canRead()) {
                return Result.failure()
            }
            val bytes = file.readBytes()
            if (contentHash.isNotEmpty()) {
                val actual = sha256Hex(bytes)
                if (actual != contentHash) {
                    // EDGE: local PDF corrupt — refuse fake resume.
                    prefs.edit().remove(KEY_DRAFT).apply()
                    return Result.failure()
                }
            }
            val size = if (bytesLen > 0) bytesLen else bytes.size.toLong()
            activeJobId = resumeChunks(
                session = session,
                uploadId = uploadId,
                filename = filename,
                contentHash = contentHash,
                bytes = bytes,
                size = size,
                draft = draft,
                prefs = prefs,
            )
        }

        if (activeJobId.isEmpty()) {
            return Result.failure()
        }

        val cacheId = pollJob(session, activeJobId)
        if (cacheId.isNullOrBlank()) {
            UploadForegroundService.update(
                applicationContext,
                "업로드 중단됨",
                "앱을 열면 이어갈 수 있습니다",
                null,
            )
            return Result.retry()
        }

        // Success: clear draft (keep PDF delete best-effort).
        val path = draft.optString("local_path", "")
        prefs.edit().remove(KEY_DRAFT).apply()
        if (path.contains("ingest_drafts")) {
            try {
                File(path).delete()
            } catch (_: Exception) {
            }
        }
        // Pending open for Flutter (same key as Dart).
        prefs.edit().putString(KEY_PENDING_OPEN, cacheId).apply()
        UploadForegroundService.update(
            applicationContext,
            "업로드 완료",
            "탭하면 읽기로 이동합니다",
            cacheId,
        )
        return Result.success()
    }

    private fun resumeChunks(
        session: String,
        uploadId: String,
        filename: String,
        contentHash: String,
        bytes: ByteArray,
        size: Long,
        draft: JSONObject,
        prefs: android.content.SharedPreferences,
    ): String {
        val st = getJson(session, "/api/ingest/uploads/${enc(uploadId)}")
        var offset = st.optLong("received_offset", 0L).toInt().coerceAtLeast(0)
        val chunkSize = st.optInt("chunk_size", CHUNK).let { if (it > 0) it else CHUNK }
        val remoteHash = st.optString("content_hash", "").lowercase()
        if (remoteHash.isNotEmpty() && contentHash.isNotEmpty() && remoteHash != contentHash) {
            throw IllegalStateException("hash_mismatch")
        }
        if (offset > 0) {
            val prefix = sha256Hex(bytes.copyOfRange(0, offset.coerceAtMost(bytes.size)))
            val want = st.optString("prefix_sha256", "").lowercase()
            if (want.isNotEmpty() && prefix != want) {
                throw IllegalStateException("prefix_mismatch")
            }
        }
        while (offset < bytes.size) {
            val end = (offset + chunkSize).coerceAtMost(bytes.size)
            val slice = bytes.copyOfRange(offset, end)
            val chunkSha = sha256Hex(slice)
            putChunk(session, uploadId, offset, slice, chunkSha)
            offset = end
            val pct = ((offset * 100L) / bytes.size).toInt().coerceIn(0, 99)
            UploadForegroundService.update(
                applicationContext,
                "PDF 올리는 중",
                "조각 올리는 중 · $pct%",
                null,
            )
        }
        val completed = postJson(session, "/api/ingest/uploads/${enc(uploadId)}/complete", "{}")
        val jobId = completed.optString("job_id", "").trim()
        if (jobId.isEmpty()) throw IllegalStateException("missing_job_id")
        draft.put("job_id", jobId)
        draft.put("phase", "processing")
        draft.put("upload_id", uploadId)
        draft.put("filename", filename)
        draft.put("content_hash", contentHash)
        draft.put("bytes_len", size)
        prefs.edit().putString(KEY_DRAFT, draft.toString()).apply()
        return jobId
    }

    private fun pollJob(session: String, jobId: String): String? {
        val deadline = System.currentTimeMillis() + TimeUnit.MINUTES.toMillis(45)
        while (System.currentTimeMillis() < deadline) {
            val st = getJson(session, "/api/ingest/jobs/${enc(jobId)}")
            val done = st.optBoolean("done", false)
            val pct = st.optInt("percent", 0).coerceIn(0, 100)
            val msg = st.optString("message", "처리 중").ifBlank { "처리 중" }
            UploadForegroundService.update(
                applicationContext,
                "PDF 올리는 중",
                sanitize("$msg · $pct%"),
                null,
            )
            if (done) {
                val err = st.optString("error", "")
                val cacheId = st.optString("cache_id", "").trim()
                if (cacheId.isNotEmpty()) return cacheId
                if (err.isNotEmpty()) return null
                val result = st.optJSONObject("result")
                val nested = result?.optString("cache_id", "")?.trim().orEmpty()
                return nested.ifEmpty { null }
            }
            Thread.sleep(2000)
        }
        return null
    }

    private fun getJson(session: String, path: String): JSONObject {
        val conn = open(session, path, "GET")
        return readJson(conn)
    }

    private fun postJson(session: String, path: String, body: String): JSONObject {
        val conn = open(session, path, "POST")
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        conn.doOutput = true
        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(body) }
        return readJson(conn)
    }

    private fun putChunk(
        session: String,
        uploadId: String,
        offset: Int,
        data: ByteArray,
        chunkSha: String,
    ) {
        val path = "/api/ingest/uploads/${enc(uploadId)}?offset=$offset"
        val conn = open(session, path, "PUT")
        conn.setRequestProperty("Content-Type", "application/octet-stream")
        conn.setRequestProperty("X-Chunk-Sha256", chunkSha)
        conn.doOutput = true
        conn.outputStream.use { it.write(data) }
        val code = conn.responseCode
        if (code !in 200..299) {
            throw IllegalStateException("put_http_$code")
        }
        // Drain body.
        try {
            conn.inputStream?.close()
        } catch (_: Exception) {
        }
    }

    private fun open(session: String, path: String, method: String): HttpURLConnection {
        val url = URL(BASE + path)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 30_000
            readTimeout = 120_000
            setRequestProperty("Accept", "application/json")
            // WHY: session from prefs only — never logged.
            setRequestProperty("Cookie", "asr_session=$session")
        }
        return conn
    }

    private fun readJson(conn: HttpURLConnection): JSONObject {
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (code !in 200..299) {
            throw IllegalStateException("http_$code")
        }
        return JSONObject(text.ifEmpty { "{}" })
    }

    private fun enc(s: String): String = java.net.URLEncoder.encode(s, "UTF-8")

    private fun sha256Hex(data: ByteArray): String {
        val d = MessageDigest.getInstance("SHA-256").digest(data)
        return d.joinToString("") { b -> "%02x".format(b) }
    }

    private fun sanitize(s: String): String {
        var t = s.trim()
        if (t.length > 96) t = t.substring(0, 93) + "…"
        if (t.contains("@") || t.contains("asr_session")) return "처리 중"
        return t
    }

    private fun buildForegroundInfo(title: String, text: String): ForegroundInfo {
        UploadForegroundService.start(applicationContext, title, text)
        val notification = androidx.core.app.NotificationCompat.Builder(
            applicationContext,
            UploadForegroundService.CHANNEL_ID,
        )
            .setContentTitle(title.take(64))
            .setContentText(text.take(96))
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
        return if (android.os.Build.VERSION.SDK_INT >= 29) {
            ForegroundInfo(
                UploadForegroundService.NOTIF_ID,
                notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            ForegroundInfo(UploadForegroundService.NOTIF_ID, notification)
        }
    }

    companion object {
        private const val TAG = "UploadResumeWorker"
        private const val FLUTTER_PREFS = "FlutterSharedPreferences"
        private const val KEY_SESSION = "flutter.asr.session.v1"
        private const val KEY_DRAFT = "flutter.asr.upload_draft.v1"
        private const val KEY_PENDING_OPEN = "flutter.asr.upload.pending_open_cache_id.v1"
        private const val BASE =
            "https://asr-sentence-reading-984608876300.asia-northeast3.run.app"
        private const val CHUNK = 256 * 1024
    }
}
