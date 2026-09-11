package com.gjtuc.sentence_reading

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import androidx.documentfile.provider.DocumentFile
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.util.concurrent.Executors
import kotlin.math.min

/**
 * design/226 — OPEN_DOCUMENT_TREE list + stream hash/read (no broad storage perms).
 * Evidence/Dart must never log full URIs or folder paths from here as product copy.
 */
class SafTreeHandler(
    private val activity: Activity,
) : MethodChannel.MethodCallHandler {
    private var pendingPick: MethodChannel.Result? = null
    private val io = Executors.newFixedThreadPool(2)
    /** design/228 — separate pool so hash pump is not starved by PdfBox. */
    private val headIo = Executors.newFixedThreadPool(2)

    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != REQ_TREE) return false
        val result = pendingPick
        pendingPick = null
        if (result == null) return true
        if (resultCode != Activity.RESULT_OK || data?.data == null) {
            result.success(null)
            return true
        }
        val uri = data.data!!
        try {
            val flags = data.flags and
                (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            activity.contentResolver.takePersistableUriPermission(
                uri,
                flags or Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        } catch (_: SecurityException) {
            // EDGE: some providers omit persistable — listing may still work this session.
        } catch (_: Exception) {
        }
        val label = DocumentFile.fromTreeUri(activity, uri)?.name?.trim().orEmpty()
        result.success(
            mapOf(
                "treeUri" to uri.toString(),
                "displayLabel" to label.ifEmpty { "폴더" },
            ),
        )
        return true
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "pickTree" -> {
                if (pendingPick != null) {
                    result.error("busy", "tree_pick_in_progress", null)
                    return
                }
                pendingPick = result
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                    if (Build.VERSION.SDK_INT >= 26) {
                        putExtra(DocumentsContract.EXTRA_INITIAL_URI, null as Uri?)
                    }
                }
                try {
                    activity.startActivityForResult(intent, REQ_TREE)
                } catch (e: Exception) {
                    pendingPick = null
                    result.error("pick_fail", e.message, null)
                }
            }
            "releaseTree" -> {
                val treeUri = call.argument<String>("treeUri")?.trim().orEmpty()
                if (treeUri.isEmpty()) {
                    result.success(false)
                    return
                }
                try {
                    activity.contentResolver.releasePersistableUriPermission(
                        Uri.parse(treeUri),
                        Intent.FLAG_GRANT_READ_URI_PERMISSION,
                    )
                    result.success(true)
                } catch (_: Exception) {
                    result.success(false)
                }
            }
            "listPdfs" -> {
                val treeUri = call.argument<String>("treeUri")?.trim().orEmpty()
                val maxItems = call.argument<Int>("maxItems") ?: MAX_LIST
                if (treeUri.isEmpty()) {
                    result.error("bad_args", "treeUri_required", null)
                    return
                }
                io.execute {
                    try {
                        val root = DocumentFile.fromTreeUri(activity, Uri.parse(treeUri))
                        if (root == null || !root.canRead()) {
                            activity.runOnUiThread {
                                result.error("stale", "cannot_read_tree", null)
                            }
                            return@execute
                        }
                        val out = ArrayList<Map<String, Any?>>(min(maxItems, 64))
                        var truncated = false
                        fun walk(dir: DocumentFile) {
                            if (out.size >= maxItems) {
                                truncated = true
                                return
                            }
                            val children = try {
                                dir.listFiles()
                            } catch (_: SecurityException) {
                                truncated = true
                                return
                            } catch (_: Exception) {
                                return
                            }
                            for (f in children) {
                                if (out.size >= maxItems) {
                                    truncated = true
                                    return
                                }
                                if (f.isDirectory) {
                                    walk(f)
                                    if (truncated) return
                                    continue
                                }
                                val name = f.name?.trim().orEmpty()
                                val mime = f.type?.trim().orEmpty()
                                val isPdf = name.endsWith(".pdf", ignoreCase = true) ||
                                    mime.equals("application/pdf", ignoreCase = true)
                                if (!isPdf) continue
                                val uri = f.uri?.toString()?.trim().orEmpty()
                                if (uri.isEmpty() || name.isEmpty()) continue
                                out.add(
                                    mapOf(
                                        "docUri" to uri,
                                        "displayName" to name,
                                        "sizeBytes" to f.length(),
                                        "lastModifiedMs" to f.lastModified(),
                                    ),
                                )
                            }
                        }
                        walk(root)
                        out.sortBy { (it["displayName"] as? String)?.lowercase() ?: "" }
                        activity.runOnUiThread {
                            result.success(
                                mapOf(
                                    "items" to out,
                                    "truncated" to truncated,
                                    "n" to out.size,
                                ),
                            )
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("stale", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("list_fail", e.message, null)
                        }
                    }
                }
            }
            "sha256OfUri" -> {
                val docUri = call.argument<String>("docUri")?.trim().orEmpty()
                if (docUri.isEmpty()) {
                    result.error("bad_args", "docUri_required", null)
                    return
                }
                io.execute {
                    try {
                        val hex = sha256Stream(Uri.parse(docUri))
                        activity.runOnUiThread {
                            if (hex == null) result.error("hash_fail", "null", null)
                            else result.success(hex)
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("stale", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("hash_fail", e.message, null)
                        }
                    }
                }
            }
            "readPdfBytes" -> {
                val docUri = call.argument<String>("docUri")?.trim().orEmpty()
                val maxBytes = call.argument<Int>("maxBytes") ?: MAX_BYTES
                if (docUri.isEmpty()) {
                    result.error("bad_args", "docUri_required", null)
                    return
                }
                io.execute {
                    try {
                        val bytes = readLimited(Uri.parse(docUri), maxBytes)
                        activity.runOnUiThread {
                            if (bytes == null) result.error("read_fail", "null", null)
                            else result.success(bytes)
                        }
                    } catch (e: TooLargeException) {
                        activity.runOnUiThread {
                            result.error("too_large", "max_$maxBytes", null)
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("stale", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("read_fail", e.message, null)
                        }
                    }
                }
            }
            // design/228 — advisory head extract (title / SI markers).
            "extractPdfHead" -> {
                val docUri = call.argument<String>("docUri")?.trim().orEmpty()
                val maxChars = call.argument<Int>("maxChars") ?: 8000
                val maxPages = call.argument<Int>("maxPages") ?: 2
                val maxReadBytes = call.argument<Int>("maxReadBytes") ?: (50 * 1024 * 1024)
                if (docUri.isEmpty()) {
                    result.error("bad_args", "docUri_required", null)
                    return
                }
                headIo.execute {
                    try {
                        val map = PdfHeadExtract.extract(
                            activity,
                            Uri.parse(docUri),
                            maxChars,
                            maxPages,
                            maxReadBytes,
                        )
                        activity.runOnUiThread { result.success(map) }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("stale", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("extract_fail", e.message, null)
                        }
                    }
                }
            }
            else -> result.notImplemented()
        }
    }

    private fun sha256Stream(uri: Uri): String? {
        val md = MessageDigest.getInstance("SHA-256")
        activity.contentResolver.openInputStream(uri)?.use { input ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                md.update(buf, 0, n)
            }
        } ?: return null
        return md.digest().joinToString("") { b -> "%02x".format(b) }
    }

    private fun readLimited(uri: Uri, maxBytes: Int): ByteArray? {
        activity.contentResolver.openInputStream(uri)?.use { input ->
            val out = ByteArrayOutputStream()
            val buf = ByteArray(64 * 1024)
            var total = 0
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                total += n
                if (total > maxBytes) throw TooLargeException()
                out.write(buf, 0, n)
            }
            return out.toByteArray()
        }
        return null
    }

    private class TooLargeException : Exception()

    companion object {
        const val CHANNEL = "asr/saf_tree"
        private const val REQ_TREE = 9261
        private const val MAX_LIST = 500
        private const val MAX_BYTES = 50 * 1024 * 1024
    }
}
