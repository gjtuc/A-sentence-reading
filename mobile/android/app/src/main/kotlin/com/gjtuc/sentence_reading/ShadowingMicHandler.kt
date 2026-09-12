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
 * design/82 + design/245 — AAC practice takes via MediaRecorder.
 * INVARIANT: never log paths that could include user PII beyond cache temp names.
 * Fail-closed: permission denied / IO → success(false) or error string, never fake bytes.
 *
 * design/245: [prepare] builds+prepares without start so Speak can [start] with less latency.
 */
internal class ShadowingMicHandler(
    private val activity: MainActivity,
) : MethodChannel.MethodCallHandler {
    private var recorder: MediaRecorder? = null
    private var activePath: String? = null
    /** True after successful [prepare], before [start]. */
    private var primed: Boolean = false

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
            "prepare" -> {
                val path = call.argument<String>("path")?.trim().orEmpty()
                if (path.isEmpty()) {
                    result.error("bad_path", "path required", null)
                    return
                }
                if (!hasPermission()) {
                    result.success(false)
                    return
                }
                result.success(prepareRecorder(path))
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
                // design/245 — primed path: only start().
                if (primed && recorder != null && activePath == path) {
                    try {
                        recorder!!.start()
                        primed = false
                        result.success(true)
                    } catch (e: Exception) {
                        stopQuiet()
                        result.success(buildAndStart(path))
                    }
                    return
                }
                result.success(buildAndStart(path))
            }
            "stop" -> {
                val path = activePath
                try {
                    recorder?.apply {
                        try {
                            // EDGE: stop() on primed-but-not-started throws — release only.
                            if (!primed) {
                                stop()
                            }
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
                    primed = false
                }
                result.success(path)
            }
            else -> result.notImplemented()
        }
    }

    private fun prepareRecorder(path: String): Boolean {
        return try {
            stopQuiet()
            val file = File(path)
            file.parentFile?.mkdirs()
            val mr = newRecorder()
            configure(mr, path)
            mr.prepare()
            recorder = mr
            activePath = path
            primed = true
            true
        } catch (_: Exception) {
            stopQuiet()
            false
        }
    }

    private fun buildAndStart(path: String): Boolean {
        return try {
            stopQuiet()
            val file = File(path)
            file.parentFile?.mkdirs()
            val mr = newRecorder()
            configure(mr, path)
            mr.prepare()
            mr.start()
            recorder = mr
            activePath = path
            primed = false
            true
        } catch (_: Exception) {
            stopQuiet()
            false
        }
    }

    private fun newRecorder(): MediaRecorder {
        return if (Build.VERSION.SDK_INT >= 31) {
            MediaRecorder(activity)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
    }

    private fun configure(mr: MediaRecorder, path: String) {
        mr.setAudioSource(MediaRecorder.AudioSource.MIC)
        mr.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        mr.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        mr.setAudioEncodingBitRate(128_000)
        mr.setAudioSamplingRate(44_100)
        mr.setOutputFile(path)
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
                    if (!primed) {
                        stop()
                    }
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
            primed = false
        }
    }

    companion object {
        const val CHANNEL = "asr/shadowing_mic"
        private const val REQ_MIC = 742
    }
}
