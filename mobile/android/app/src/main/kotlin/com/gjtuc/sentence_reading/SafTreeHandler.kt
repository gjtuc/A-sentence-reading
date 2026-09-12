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
import java.text.Normalizer
import java.security.MessageDigest
import java.util.concurrent.Executors
import kotlin.math.min

/**
 * design/226 — OPEN_DOCUMENT_TREE list + stream hash/read (no broad storage perms).
 * design/238 — OPEN_DOCUMENT pick (temp read).
 * design/241 — probeTreeWritable + copyUriIntoTree (createFile + 64KiB stream).
 * design/247 — Downloads DocumentsContract INITIAL_URI (not MediaStore).
 * design/249 — list/copy PDF + DOCX.
 * Evidence/Dart must never log full URIs or folder paths from here as product copy.
 */
class SafTreeHandler(
    private val activity: Activity,
) : MethodChannel.MethodCallHandler {
    private var pendingPick: MethodChannel.Result? = null
    private var pendingPickDocs: MethodChannel.Result? = null
    private val io = Executors.newFixedThreadPool(2)
    /** design/228 — separate pool so hash pump is not starved by PdfBox. */
    private val headIo = Executors.newFixedThreadPool(2)

    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        when (requestCode) {
            REQ_TREE -> {
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
                        flags or
                            Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
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
            REQ_DOCS -> {
                val result = pendingPickDocs
                pendingPickDocs = null
                if (result == null) return true
                if (resultCode != Activity.RESULT_OK || data == null) {
                    result.success(null)
                    return true
                }
                val out = ArrayList<Map<String, Any?>>()
                fun addUri(uri: Uri) {
                    val doc = DocumentFile.fromSingleUri(activity, uri) ?: return
                    val name = doc.name?.trim().orEmpty()
                    if (name.isEmpty()) return
                    val lower = name.lowercase()
                    // design/253 — PDF + DOCX only (name filter; MIME may be octet-stream).
                    if (!lower.endsWith(".pdf") && !lower.endsWith(".docx")) return
                    out.add(
                        mapOf(
                            "docUri" to uri.toString(),
                            "displayName" to name,
                            "sizeBytes" to doc.length(),
                            "lastModifiedMs" to doc.lastModified(),
                        ),
                    )
                }
                val clip = data.clipData
                if (clip != null && clip.itemCount > 0) {
                    for (i in 0 until clip.itemCount) {
                        val u = clip.getItemAt(i)?.uri ?: continue
                        addUri(u)
                    }
                } else {
                    data.data?.let { addUri(it) }
                }
                result.success(if (out.isEmpty()) null else out)
                return true
            }
            else -> return false
        }
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "pickTree" -> {
                if (pendingPick != null || pendingPickDocs != null) {
                    result.error("busy", "tree_pick_in_progress", null)
                    return
                }
                pendingPick = result
                val initialUriArg = call.argument<String>("initialUri")?.trim().orEmpty()
                val targetUri = if (initialUriArg.isNotEmpty()) {
                    try {
                        Uri.parse(initialUriArg)
                    } catch (_: Exception) {
                        downloadsDocumentUri()
                    }
                } else {
                    downloadsDocumentUri()
                }
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                    addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                    // design/247 · 253 · 254 — prefer caller-provided initialUri (e.g. current tree), fallback to Downloads.
                    if (Build.VERSION.SDK_INT >= 26) {
                        putExtra(
                            DocumentsContract.EXTRA_INITIAL_URI,
                            targetUri,
                        )
                    }
                }
                try {
                    activity.startActivityForResult(intent, REQ_TREE)
                } catch (e: Exception) {
                    pendingPick = null
                    result.error("pick_fail", e.message, null)
                }
            }
            "pickDocuments" -> {
                if (pendingPick != null || pendingPickDocs != null) {
                    result.error("busy", "docs_pick_in_progress", null)
                    return
                }
                pendingPickDocs = result
                val multiple = call.argument<Boolean>("multiple") ?: true
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    // design/253 — PDF + DOCX from Downloads.
                    type = "*/*"
                    putExtra(
                        Intent.EXTRA_MIME_TYPES,
                        arrayOf(
                            "application/pdf",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ),
                    )
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, multiple)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    // design/247 — DocumentsContract document URI (MediaStore is ignored).
                    if (Build.VERSION.SDK_INT >= 26) {
                        putExtra(
                            DocumentsContract.EXTRA_INITIAL_URI,
                            downloadsDocumentUri(),
                        )
                    }
                }
                try {
                    activity.startActivityForResult(intent, REQ_DOCS)
                } catch (e: Exception) {
                    pendingPickDocs = null
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
                        Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                    )
                    result.success(true)
                } catch (_: Exception) {
                    result.success(false)
                }
            }
            "normalizeNfkc" -> {
                val text = call.argument<String>("text") ?: ""
                io.execute {
                    val out = try {
                        Normalizer.normalize(text, Normalizer.Form.NFKC)
                    } catch (_: Exception) {
                        text
                    }
                    activity.runOnUiThread {
                        result.success(mapOf("text" to out))
                    }
                }
            }
            "probeTreeWritable" -> {
                val treeUri = call.argument<String>("treeUri")?.trim().orEmpty()
                if (treeUri.isEmpty()) {
                    result.error("bad_args", "treeUri_required", null)
                    return
                }
                io.execute {
                    try {
                        val root = DocumentFile.fromTreeUri(activity, Uri.parse(treeUri))
                        val writable = root != null && root.canWrite()
                        activity.runOnUiThread {
                            result.success(
                                mapOf(
                                    "writable" to writable,
                                    "code" to if (writable) "ok" else "not_writable",
                                ),
                            )
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.success(
                                mapOf("writable" to false, "code" to "stale"),
                            )
                        }
                    } catch (_: Exception) {
                        activity.runOnUiThread {
                            result.success(
                                mapOf("writable" to false, "code" to "not_writable"),
                            )
                        }
                    }
                }
            }
            "writeBytesIntoTree" -> {
                val treeUri = call.argument<String>("treeUri")?.trim().orEmpty()
                val displayNameArg = call.argument<String>("displayName")?.trim().orEmpty()
                val bytes = call.argument<ByteArray>("bytes")
                if (treeUri.isEmpty() || displayNameArg.isEmpty() || bytes == null || bytes.isEmpty()) {
                    result.error("bad_args", "tree_name_bytes_required", null)
                    return
                }
                if (bytes.size.toLong() > MAX_BYTES) {
                    result.error("too_large", "max_$MAX_BYTES", null)
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
                        if (!root.canWrite()) {
                            activity.runOnUiThread {
                                result.error("not_writable", "tree_not_writable", null)
                            }
                            return@execute
                        }
                        val unique = uniqueDocName(root, displayNameArg)
                        val mime = mimeForDocName(unique)
                        val created = root.createFile(mime, unique.stripDocExt())
                        if (created == null || created.uri == null) {
                            activity.runOnUiThread {
                                result.error("create_fail", "createFile_null", null)
                            }
                            return@execute
                        }
                        try {
                            activity.contentResolver.openOutputStream(created.uri!!)?.use { out ->
                                out.write(bytes)
                                out.flush()
                            } ?: run {
                                try {
                                    created.delete()
                                } catch (_: Exception) {
                                }
                                activity.runOnUiThread {
                                    result.error("write_fail", "openOutputStream_null", null)
                                }
                                return@execute
                            }
                        } catch (e: SecurityException) {
                            try {
                                created.delete()
                            } catch (_: Exception) {
                            }
                            activity.runOnUiThread {
                                result.error("stale", e.message, null)
                            }
                            return@execute
                        } catch (e: Exception) {
                            try {
                                created.delete()
                            } catch (_: Exception) {
                            }
                            activity.runOnUiThread {
                                result.error("write_fail", e.message, null)
                            }
                            return@execute
                        }
                        val name = created.name?.trim().orEmpty().ifEmpty { unique }
                        activity.runOnUiThread {
                            result.success(
                                mapOf(
                                    "docUri" to created.uri!!.toString(),
                                    "displayName" to name,
                                    "sizeBytes" to created.length(),
                                    "lastModifiedMs" to created.lastModified(),
                                ),
                            )
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("stale", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("write_fail", e.message, null)
                        }
                    }
                }
            }

            "copyUriIntoTree" -> {
                val srcDocUri = call.argument<String>("srcDocUri")?.trim().orEmpty()
                val treeUri = call.argument<String>("treeUri")?.trim().orEmpty()
                val displayNameArg = call.argument<String>("displayName")?.trim().orEmpty()
                if (srcDocUri.isEmpty() || treeUri.isEmpty()) {
                    result.error("bad_args", "src_or_tree_required", null)
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
                        if (!root.canWrite()) {
                            activity.runOnUiThread {
                                result.error("not_writable", "tree_not_writable", null)
                            }
                            return@execute
                        }
                        val src = DocumentFile.fromSingleUri(activity, Uri.parse(srcDocUri))
                        val baseName = when {
                            displayNameArg.isNotEmpty() -> displayNameArg
                            src?.name?.trim()?.isNotEmpty() == true -> src!!.name!!.trim()
                            else -> "document.pdf"
                        }
                        val unique = uniqueDocName(root, baseName)
                        val mime = mimeForDocName(unique)
                        val created = root.createFile(mime, unique.stripDocExt())
                        if (created == null || created.uri == null) {
                            activity.runOnUiThread {
                                result.error("create_fail", "createFile_null", null)
                            }
                            return@execute
                        }
                        try {
                            streamCopy(Uri.parse(srcDocUri), created.uri!!, MAX_BYTES)
                        } catch (e: TooLargeException) {
                            try {
                                created.delete()
                            } catch (_: Exception) {
                            }
                            activity.runOnUiThread {
                                result.error("too_large", "max_$MAX_BYTES", null)
                            }
                            return@execute
                        } catch (e: SecurityException) {
                            try {
                                created.delete()
                            } catch (_: Exception) {
                            }
                            activity.runOnUiThread {
                                result.error("stale", e.message, null)
                            }
                            return@execute
                        } catch (e: Exception) {
                            try {
                                created.delete()
                            } catch (_: Exception) {
                            }
                            activity.runOnUiThread {
                                result.error("copy_fail", e.message, null)
                            }
                            return@execute
                        }
                        val name = created.name?.trim().orEmpty().ifEmpty { unique }
                        activity.runOnUiThread {
                            result.success(
                                mapOf(
                                    "docUri" to created.uri!!.toString(),
                                    "displayName" to name,
                                    "sizeBytes" to created.length(),
                                    "lastModifiedMs" to created.lastModified(),
                                ),
                            )
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("stale", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("copy_fail", e.message, null)
                        }
                    }
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
                                val isDocx = name.endsWith(".docx", ignoreCase = true) ||
                                    mime.equals(
                                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        ignoreCase = true,
                                    )
                                if (!isPdf && !isDocx) continue
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
            // design/254 — DOCX head extract (word/document.xml + docProps/core.xml).
            "extractDocxHead" -> {
                val docUri = call.argument<String>("docUri")?.trim().orEmpty()
                val maxChars = call.argument<Int>("maxChars") ?: 8000
                val maxReadBytes = call.argument<Int>("maxReadBytes") ?: (50 * 1024 * 1024)
                if (docUri.isEmpty()) {
                    result.error("bad_args", "docUri_required", null)
                    return
                }
                headIo.execute {
                    try {
                        val map = DocxHeadExtract.extract(
                            activity,
                            Uri.parse(docUri),
                            maxChars = maxChars,
                            maxReadBytes = maxReadBytes,
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
            // design/254 — delete document from SAF tree or downloads.
            "deleteDocument" -> {
                val docUri = call.argument<String>("docUri")?.trim().orEmpty()
                if (docUri.isEmpty()) {
                    result.error("bad_args", "docUri_required", null)
                    return
                }
                io.execute {
                    try {
                        val uri = Uri.parse(docUri)
                        val ok = DocumentsContract.deleteDocument(activity.contentResolver, uri)
                        activity.runOnUiThread {
                            result.success(ok)
                        }
                    } catch (e: SecurityException) {
                        activity.runOnUiThread {
                            result.error("security_error", e.message, null)
                        }
                    } catch (e: Exception) {
                        activity.runOnUiThread {
                            result.error("delete_fail", e.message, null)
                        }
                    }
                }
            }
            else -> result.notImplemented()
        }
    }

    /** design/247 — OPEN_DOCUMENT hint: primary Download as DocumentsProvider document. */
    private fun downloadsDocumentUri(): Uri {
        return DocumentsContract.buildDocumentUri(
            EXTERNAL_STORAGE_PROVIDER,
            "primary:Download",
        )
    }

    /** design/247 — OPEN_DOCUMENT_TREE hint: primary Download as tree root. */
    private fun downloadsTreeUri(): Uri {
        return DocumentsContract.buildTreeDocumentUri(
            EXTERNAL_STORAGE_PROVIDER,
            "primary:Download",
        )
    }

    private fun mimeForDocName(name: String): String {
        return if (name.lowercase().endsWith(".docx")) {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        } else {
            "application/pdf"
        }
    }

    /** design/249 — unique name preserving .pdf / .docx. */
    private fun uniqueDocName(root: DocumentFile, desired: String): String {
        var base = desired.trim().ifEmpty { "document.pdf" }
        val lower = base.lowercase()
        val isDocx = lower.endsWith(".docx")
        val isPdf = lower.endsWith(".pdf")
        if (!isDocx && !isPdf) {
            base = "$base.pdf"
        }
        val ext = if (base.lowercase().endsWith(".docx")) ".docx" else ".pdf"
        val existing = try {
            root.listFiles().mapNotNull { it.name?.trim()?.lowercase() }.toSet()
        } catch (_: Exception) {
            emptySet()
        }
        if (base.lowercase() !in existing) return base
        val stem = base.substring(0, base.length - ext.length)
        var i = 1
        while (i < 1000) {
            val candidate = "$stem ($i)$ext"
            if (candidate.lowercase() !in existing) return candidate
            i += 1
        }
        return "$stem (${System.currentTimeMillis()})$ext"
    }

    private fun String.stripDocExt(): String {
        val lower = lowercase()
        return when {
            lower.endsWith(".docx") -> substring(0, length - 5)
            lower.endsWith(".pdf") -> substring(0, length - 4)
            else -> this
        }
    }

    private fun uniquePdfName(root: DocumentFile, desired: String): String {
        return uniqueDocName(root, desired)
    }

    private fun String.stripPdfExt(): String {
        return stripDocExt()
    }

    private fun streamCopy(src: Uri, dest: Uri, maxBytes: Int) {
        activity.contentResolver.openInputStream(src)?.use { input ->
            activity.contentResolver.openOutputStream(dest)?.use { output ->
                val buf = ByteArray(64 * 1024)
                var total = 0
                while (true) {
                    val n = input.read(buf)
                    if (n <= 0) break
                    total += n
                    if (total > maxBytes) throw TooLargeException()
                    output.write(buf, 0, n)
                }
                output.flush()
            } ?: throw Exception("openOutputStream_null")
        } ?: throw Exception("openInputStream_null")
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
        private const val REQ_DOCS = 9262
        private const val MAX_LIST = 500
        private const val MAX_BYTES = 50 * 1024 * 1024
        private const val EXTERNAL_STORAGE_PROVIDER =
            "com.android.externalstorage.documents"
    }
}
