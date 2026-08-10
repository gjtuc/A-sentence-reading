package com.gjtuc.sentence_reading

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * design/82 — AAC practice takes via MediaRecorder (no pub.dev `record` package).
 * INVARIANT: never log paths that could include user PII beyond cache temp names.
 * Fail-closed: permission denied / IO → success(false) or error string, never fake bytes.
 */
internal class ShadowingMicHandler(
    private val activity: MainActivity,
) : MethodChannel.MethodCallHandler {
    private var recorder: MediaRecorder? = null
    private var activePath: String? = null

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "hasPermission" -> {
                result.success(hasPermission())
            }
            "requestPermission" -> {
                if (hasPermission()) {
                    result.success(true)
                    return
                }
                ActivityCompat.requestPermissions(
                    activity,
                    arrayOf(Manifest.permission.RECORD_AUDIO),
                    REQ_MIC,
                )
                // EDGE: async grant — caller may need a second hasPermission check.
                result.success(hasPermission())
            }
            "start" -> {
                val path = call.argument<String>("path")?.trim().orEmpty()
                if (path.isEmpty()) {
                    result.error("bad_path", "path required", null)
                    return
                }
                if (!hasPermission()) {
                    result.success(false)
                    return
                }
                try {
                    stopQuiet()
                    val file = File(path)
                    file.parentFile?.mkdirs()
                    val mr = if (Build.VERSION.SDK_INT >= 31) {
                        MediaRecorder(activity)
                    } else {
                        @Suppress("DEPRECATION")
                        MediaRecorder()
                    }
                    mr.setAudioSource(MediaRecorder.AudioSource.MIC)
                    mr.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                    mr.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                    mr.setAudioEncodingBitRate(128_000)
                    mr.setAudioSamplingRate(44_100)
                    mr.setOutputFile(path)
                    mr.prepare()
                    mr.start()
                    recorder = mr
                    activePath = path
                    result.success(true)
                } catch (e: Exception) {
                    stopQuiet()
                    result.success(false)
                }
            }
            "stop" -> {
                val path = activePath
                try {
                    recorder?.apply {
                        try {
                            stop()
                        } catch (_: Exception) {
                        }
                        try {
                            release()
                        } catch (_: Exception) {
                        }
                    }
                } finally {
                    recorder = null
                    activePath = null
                }
                result.success(path)
            }
            else -> result.notImplemented()
        }
    }

    private fun hasPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            activity,
            Manifest.permission.RECORD_AUDIO,
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun stopQuiet() {
        try {
            recorder?.apply {
                try {
                    stop()
                } catch (_: Exception) {
                }
                try {
                    release()
                } catch (_: Exception) {
                }
            }
        } finally {
            recorder = null
            activePath = null
        }
    }

    companion object {
        const val CHANNEL = "asr/shadowing_mic"
        private const val REQ_MIC = 742
    }
}
