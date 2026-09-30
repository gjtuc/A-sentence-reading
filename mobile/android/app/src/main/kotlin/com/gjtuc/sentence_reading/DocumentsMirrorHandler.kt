package com.gjtuc.sentence_reading

import android.app.Activity
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * design/264 — public Documents/문장읽기 mirror via MANAGE_EXTERNAL_STORAGE.
 * Import (226/242) must not use this channel.
 */
class DocumentsMirrorHandler(
    private val activity: Activity,
) : MethodChannel.MethodCallHandler {
    companion object {
        const val CHANNEL = "asr/documents_mirror"
        private const val NOMEDIA_NAME = ".nomedia"
        private const val ROOT_NAME = "문장읽기"
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "hasManagePermission" -> result.success(hasManagePermission())
            "requestManagePermission" -> {
                result.success(requestManagePermission())
            }
            "ensureUidRoot" -> {
                val uid = call.argument<String>("uid")?.trim().orEmpty()
                if (uid.isEmpty() || !isSafeUid(uid)) {
                    result.error("bad_uid", "uid required", null)
                    return
                }
                if (!hasManagePermission()) {
                    result.error("no_permission", "MANAGE_EXTERNAL_STORAGE required", null)
                    return
                }
                try {
                    val root = uidRoot(uid)
                    if (!root.exists() && !root.mkdirs()) {
                        result.error("mkdir", "cannot create root", null)
                        return
                    }
                    // design/372 - before anything can be written, so there is no
                    // window where a figure lands in a scanned directory.
                    ensureNoMedia()
                    result.success(mapOf("path" to root.absolutePath, "ok" to true))
                } catch (e: Exception) {
                    result.error("io", e.message, null)
                }
            }
            "uidRootExists" -> {
                val uid = call.argument<String>("uid")?.trim().orEmpty()
                if (uid.isEmpty() || !isSafeUid(uid)) {
                    result.success(false)
                    return
                }
                if (!hasManagePermission()) {
                    result.success(false)
                    return
                }
                result.success(uidRoot(uid).isDirectory)
            }
            "writeBytes" -> {
                val uid = call.argument<String>("uid")?.trim().orEmpty()
                val rel = call.argument<String>("relativePath")?.trim().orEmpty()
                val bytes = call.argument<ByteArray>("bytes")
                if (uid.isEmpty() || !isSafeUid(uid) || rel.isEmpty() || bytes == null) {
                    result.error("bad_args", "uid/relativePath/bytes", null)
                    return
                }
                if (!hasManagePermission()) {
                    result.error("no_permission", "MANAGE_EXTERNAL_STORAGE required", null)
                    return
                }
                try {
                    val f = resolveUnderUid(uid, rel)
                    f.parentFile?.mkdirs()
                    f.writeBytes(bytes)
                    result.success(true)
                } catch (e: Exception) {
                    result.error("io", e.message, null)
                }
            }
            "readBytes" -> {
                val uid = call.argument<String>("uid")?.trim().orEmpty()
                val rel = call.argument<String>("relativePath")?.trim().orEmpty()
                if (uid.isEmpty() || !isSafeUid(uid) || rel.isEmpty()) {
                    result.error("bad_args", "uid/relativePath", null)
                    return
                }
                if (!hasManagePermission()) {
                    result.error("no_permission", "MANAGE_EXTERNAL_STORAGE required", null)
                    return
                }
                try {
                    val f = resolveUnderUid(uid, rel)
                    if (!f.isFile) {
                        result.success(null)
                        return
                    }
                    result.success(f.readBytes())
                } catch (e: Exception) {
                    result.error("io", e.message, null)
                }
            }
            "deletePath" -> {
                val uid = call.argument<String>("uid")?.trim().orEmpty()
                val rel = call.argument<String>("relativePath")?.trim().orEmpty()
                if (uid.isEmpty() || !isSafeUid(uid) || rel.isEmpty()) {
                    result.error("bad_args", "uid/relativePath", null)
                    return
                }
                if (!hasManagePermission()) {
                    result.error("no_permission", "MANAGE_EXTERNAL_STORAGE required", null)
                    return
                }
                try {
                    val f = resolveUnderUid(uid, rel)
                    result.success(if (f.exists()) f.deleteRecursively() else true)
                } catch (e: Exception) {
                    result.error("io", e.message, null)
                }
            }
            "listRelative" -> {
                val uid = call.argument<String>("uid")?.trim().orEmpty()
                val rel = call.argument<String>("relativePath")?.trim().orEmpty() ?: ""
                if (uid.isEmpty() || !isSafeUid(uid)) {
                    result.error("bad_args", "uid", null)
                    return
                }
                if (!hasManagePermission()) {
                    result.error("no_permission", "MANAGE_EXTERNAL_STORAGE required", null)
                    return
                }
                try {
                    val dir = if (rel.isEmpty()) uidRoot(uid) else resolveUnderUid(uid, rel)
                    if (!dir.isDirectory) {
                        result.success(emptyList<String>())
                        return
                    }
                    val names = dir.listFiles()?.map { it.name }?.sorted() ?: emptyList()
                    result.success(names)
                } catch (e: Exception) {
                    result.error("io", e.message, null)
                }
            }
            "hideFromGallery" -> {
                if (!hasManagePermission()) {
                    result.error("no_permission", "MANAGE_EXTERNAL_STORAGE required", null)
                    return
                }
                try {
                    result.success(hideFromGallery())
                } catch (e: Exception) {
                    result.error("io", e.message, null)
                }
            }
            else -> result.notImplemented()
        }
    }

    private fun hasManagePermission(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Environment.isExternalStorageManager()
        } else {
            true
        }
    }

    private fun requestManagePermission(): Boolean {
        if (hasManagePermission()) return true
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                    data = Uri.parse("package:${activity.packageName}")
                }
                activity.startActivity(intent)
                return false
            } catch (_: Exception) {
                try {
                    activity.startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
                } catch (_: Exception) {
                }
                return false
            }
        }
        return true
    }

    /**
     * design/372 - keep mirrored figures out of gallery apps.
     *
     * The mirror has to live in public storage or it would not survive the
     * uninstall design/262 exists for, and public storage is what the media
     * scanner reads. An empty `.nomedia` marker makes the scanner skip this tree
     * and everything under it, which is the whole mirror, so a figure added later
     * is covered without another call.
     *
     * Nothing here deletes a MediaStore row. Deleting through MediaStore deletes
     * the file it points at, which would throw away the very figures the mirror
     * is keeping. A rescan is asked for instead: a directory holding `.nomedia`
     * has its indexed children dropped, and the files stay.
     */
    private fun ensureNoMedia(): Boolean {
        val root = documentsRoot()
        if (!root.exists() && !root.mkdirs()) return false
        val flag = File(root, NOMEDIA_NAME)
        if (flag.exists()) return false
        return flag.createNewFile()
    }

    private fun hideFromGallery(): Map<String, Any> {
        val root = documentsRoot()
        val created = ensureNoMedia()
        val flag = File(root, NOMEDIA_NAME)
        if (flag.isFile) {
            MediaScannerConnection.scanFile(
                activity,
                arrayOf(root.absolutePath),
                null,
                null,
            )
        }
        return mapOf(
            "ok" to flag.isFile,
            "created" to created,
            "path" to flag.absolutePath,
        )
    }

    private fun documentsRoot(): File {
        val docs = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS)
        return File(docs, ROOT_NAME)
    }

    private fun uidRoot(uid: String): File = File(documentsRoot(), uid)

    private fun isSafeUid(uid: String): Boolean {
        if (uid.length < 3 || uid.length > 128) return false
        return uid.all { it.isLetterOrDigit() || it == '_' || it == '-' }
    }

    private fun resolveUnderUid(uid: String, relativePath: String): File {
        val root = uidRoot(uid).canonicalFile
        val target = File(root, relativePath).canonicalFile
        if (!target.path.startsWith(root.path)) {
            throw SecurityException("path escape")
        }
        return target
    }
}
