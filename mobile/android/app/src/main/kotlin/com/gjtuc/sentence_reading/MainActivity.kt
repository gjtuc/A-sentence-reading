package com.gjtuc.sentence_reading

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * WHY: Single FlutterActivity host for 「문장 읽기」.
 * design/74: MethodChannel for upload FG notification (no secrets on the wire).
 * Live Enable / IPS / Trading Gate: out of scope for ASR mobile (never wired here).
 */
class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private var pendingOpenCacheId: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL,
        ).also { ch ->
            ch.setMethodCallHandler { call, result ->
                when (call.method) {
                    "startUploadNotify" -> {
                        val title = call.argument<String>("title") ?: "PDF 올리는 중"
                        val text = call.argument<String>("text") ?: "처리 중"
                        val permOk = ensureNotifyPermission()
                        if (!permOk) {
                            // Product 3A: upload may continue without FG.
                            result.success(
                                mapOf(
                                    "active" to false,
                                    "permissionDeniedHint" to true,
                                ),
                            )
                            return@setMethodCallHandler
                        }
                        try {
                            UploadForegroundService.start(this, title, text)
                            result.success(
                                mapOf(
                                    "active" to true,
                                    "permissionDeniedHint" to false,
                                ),
                            )
                        } catch (e: Exception) {
                            result.success(
                                mapOf(
                                    "active" to false,
                                    "permissionDeniedHint" to true,
                                ),
                            )
                        }
                    }
                    "updateUploadNotify" -> {
                        val title = call.argument<String>("title") ?: "PDF 올리는 중"
                        val text = call.argument<String>("text") ?: "처리 중"
                        val cacheId = call.argument<String>("cacheId")
                        try {
                            UploadForegroundService.update(this, title, text, cacheId)
                            result.success(true)
                        } catch (e: Exception) {
                            result.success(false)
                        }
                    }
                    "stopUploadNotify" -> {
                        try {
                            UploadForegroundService.stop(this)
                        } catch (_: Exception) {
                        }
                        result.success(true)
                    }
                    "takePendingOpenCacheId" -> {
                        val id = pendingOpenCacheId
                        pendingOpenCacheId = null
                        result.success(id)
                    }
                    else -> result.notImplemented()
                }
            }
        }
        // Deliver intent that launched / resumed this activity.
        handleOpenIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleOpenIntent(intent)
    }

    private fun handleOpenIntent(intent: Intent?) {
        if (intent?.action != UploadForegroundService.ACTION_OPEN_FROM_NOTIFY) return
        val id = intent.getStringExtra(UploadForegroundService.EXTRA_CACHE_ID)?.trim()
        if (id.isNullOrEmpty()) return
        pendingOpenCacheId = id
        // Notify Dart if engine is ready.
        channel?.invokeMethod("openCacheId", mapOf("cacheId" to id))
    }

    /**
     * Android 13+ POST_NOTIFICATIONS. Returns false when not granted (upload still allowed).
     */
    private fun ensureNotifyPermission(): Boolean {
        if (Build.VERSION.SDK_INT < 33) return true
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) return true
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQ_NOTIFY,
        )
        // EDGE: first call may race before user answers — treat as not yet granted.
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
    }

    companion object {
        private const val CHANNEL = "asr/upload_notify"
        private const val REQ_NOTIFY = 741
    }
}
