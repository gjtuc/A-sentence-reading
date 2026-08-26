package com.gjtuc.sentence_reading

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * WHY: Single FlutterActivity host for 「문장 읽기」.
 * design/74: MethodChannel for upload FG notification (no secrets on the wire).
 * design/76: WorkManager schedule/cancel + battery-settings guidance (no tokens on wire).
 * design/77: email magic-link VIEW intent → Dart applySessionToken.
 * design/82: shadowing practice mic (MediaRecorder MethodChannel).
 * Live Enable / IPS / Trading Gate: out of scope for ASR mobile (never wired here).
 */
class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private var authChannel: MethodChannel? = null
    private var shadowingMicChannel: MethodChannel? = null
    private var pendingOpenCacheId: String? = null
    /** design/77 — session from deep link before Dart handler is ready. */
    private var pendingMagicSession: String? = null
    private var pendingMagicError: String? = null

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
                    // design/105 — stop FG + post DEFAULT result notification (fail).
                    "showUploadFailed" -> {
                        val title = call.argument<String>("title") ?: "업로드 실패"
                        val text = call.argument<String>("text") ?: "처리에 실패했습니다."
                        try {
                            UploadForegroundService.showFailed(this, title, text)
                            result.success(true)
                        } catch (_: Exception) {
                            try {
                                UploadForegroundService.stop(this)
                            } catch (_: Exception) {
                            }
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
                    // design/76 — enqueue unique resume work (KEEP delayed / REPLACE immediate).
                    "scheduleUploadResume" -> {
                        val immediate = call.argument<Boolean>("immediate") == true
                        try {
                            UploadResumeScheduler.schedule(this, immediate)
                            result.success(true)
                        } catch (_: Exception) {
                            // EDGE: WM unavailable — fail closed (no fake scheduled=true).
                            result.success(false)
                        }
                    }
                    "cancelUploadResume" -> {
                        try {
                            UploadResumeScheduler.cancel(this)
                        } catch (_: Exception) {
                        }
                        result.success(true)
                    }
                    "isIgnoringBatteryOptimizations" -> {
                        result.success(isIgnoringBatteryOptimizations())
                    }
                    "openBatterySettings" -> {
                        result.success(openBatterySettings())
                    }
                    else -> result.notImplemented()
                }
            }
        }
        authChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            AUTH_CHANNEL,
        ).also { ch ->
            ch.setMethodCallHandler { call, result ->
                when (call.method) {
                    "takePendingMagicSession" -> {
                        val token = pendingMagicSession
                        val err = pendingMagicError
                        pendingMagicSession = null
                        pendingMagicError = null
                        result.success(
                            mapOf(
                                "token" to token,
                                "error" to err,
                            ),
                        )
                    }
                    else -> result.notImplemented()
                }
            }
        }
        // design/82 — AAC mic for practice takes (no third-party record package).
        shadowingMicChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            ShadowingMicHandler.CHANNEL,
        ).also { ch ->
            ch.setMethodCallHandler(ShadowingMicHandler(this))
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
        if (intent == null) return
        // Debuggable builds only: seed-based WM E2E without DocumentsUI (run-as + adb intent).
        if (intent.action == ACTION_DEBUG_SCHEDULE_UPLOAD_RESUME && isDebuggableApp()) {
            try {
                UploadResumeScheduler.schedule(this, immediate = true)
            } catch (_: Exception) {
            }
            return
        }
        // design/77 — custom scheme from email HTTPS bounce.
        if (intent.action == Intent.ACTION_VIEW) {
            val data = intent.data
            if (data != null && handleMagicView(data)) {
                return
            }
        }
        if (intent.action != UploadForegroundService.ACTION_OPEN_FROM_NOTIFY) return
        val id = intent.getStringExtra(UploadForegroundService.EXTRA_CACHE_ID)?.trim()
        if (id.isNullOrEmpty()) return
        pendingOpenCacheId = id
        // Notify Dart if engine is ready.
        channel?.invokeMethod("openCacheId", mapOf("cacheId" to id))
    }

    /**
     * com.gjtuc.sentence-reading://oauth/magic?asr_session=… or auth_error=…
     * INVARIANT: never log the token.
     */
    private fun handleMagicView(data: Uri): Boolean {
        // WHY (146c): hyphen scheme — underscore rejected by flutter_web_auth_2.
        if (data.scheme != "com.gjtuc.sentence-reading") return false
        if (data.host != "oauth") return false
        val path = data.path ?: ""
        if (!path.startsWith("/magic")) return false
        val err = data.getQueryParameter("auth_error")?.trim().orEmpty()
        val token = data.getQueryParameter("asr_session")?.trim().orEmpty()
        if (err.isNotEmpty()) {
            pendingMagicError = err.take(80)
            pendingMagicSession = null
            authChannel?.invokeMethod(
                "magicLinkResult",
                mapOf("error" to pendingMagicError),
            )
            return true
        }
        if (token.isEmpty() || token.equals("deleted", ignoreCase = true)) {
            pendingMagicError = "missing_session"
            pendingMagicSession = null
            authChannel?.invokeMethod(
                "magicLinkResult",
                mapOf("error" to "missing_session"),
            )
            return true
        }
        pendingMagicSession = token
        pendingMagicError = null
        authChannel?.invokeMethod(
            "magicLinkResult",
            mapOf("token" to token),
        )
        return true
    }

    private fun isDebuggableApp(): Boolean {
        return (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
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

    /**
     * design/76 product 3 — true when OS will not kill the app for "battery optimize".
     * WHY: guidance button only when restricted; never claim unrestricted without check.
     */
    private fun isIgnoringBatteryOptimizations(): Boolean {
        if (Build.VERSION.SDK_INT < 23) return true
        val pm = getSystemService(POWER_SERVICE) as? PowerManager ?: return true
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    /**
     * Open OEM battery / app-detail settings. Prefer ignore-list screen; fall back to app details.
     * INVARIANT: no REQUEST_IGNORE prompt spam — user taps intentionally.
     */
    private fun openBatterySettings(): Boolean {
        return try {
            val ignoreList = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
            if (ignoreList.resolveActivity(packageManager) != null) {
                startActivity(ignoreList)
                true
            } else {
                val detail = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:$packageName")
                }
                startActivity(detail)
                true
            }
        } catch (_: Exception) {
            false
        }
    }

    companion object {
        private const val CHANNEL = "asr/upload_notify"
        private const val AUTH_CHANNEL = "asr/auth_deeplink"
        private const val REQ_NOTIFY = 741
        /** Debuggable-only adb E2E: schedule immediate UploadResumeWorker. */
        const val ACTION_DEBUG_SCHEDULE_UPLOAD_RESUME =
            "com.gjtuc.sentence_reading.DEBUG_SCHEDULE_UPLOAD_RESUME"
    }
}
