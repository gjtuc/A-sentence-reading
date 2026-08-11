package com.gjtuc.sentence_reading

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

/**
 * design/74 — foreground service so chunk upload + job poll survive backgrounding.
 * INVARIANT: notification text must never include secrets, emails, or absolute paths
 * (Dart already sanitizes; this layer only displays provided strings).
 */
class UploadForegroundService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                releaseWakeLock()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }
            // design/105 — device E2E / Dart showFailed path (via companion.showFailed).
            ACTION_FAIL -> {
                val title = intent.getStringExtra(EXTRA_TITLE) ?: "업로드 실패"
                val text = intent.getStringExtra(EXTRA_TEXT) ?: "처리에 실패했습니다."
                releaseWakeLock()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                postFailedNotification(this, title, text)
                return START_NOT_STICKY
            }
            ACTION_UPDATE -> {
                val title = intent.getStringExtra(EXTRA_TITLE) ?: "PDF 올리는 중"
                val text = intent.getStringExtra(EXTRA_TEXT) ?: "처리 중"
                val cacheId = intent.getStringExtra(EXTRA_CACHE_ID)
                val nm = getSystemService(NotificationManager::class.java)
                nm?.notify(NOTIF_ID, buildNotification(title, text, cacheId))
                return START_STICKY
            }
            else -> {
                val title = intent?.getStringExtra(EXTRA_TITLE) ?: "PDF 올리는 중"
                val text = intent?.getStringExtra(EXTRA_TEXT) ?: "처리 중"
                ensureChannel()
                // WHY: keep CPU available for Dart HTTP chunk/poll while activity is stopped.
                acquireWakeLock()
                val notification = buildNotification(title, text, null)
                if (Build.VERSION.SDK_INT >= 29) {
                    startForeground(
                        NOTIF_ID,
                        notification,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
                    )
                } else {
                    @Suppress("DEPRECATION")
                    startForeground(NOTIF_ID, notification)
                }
                return START_STICKY
            }
        }
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(PowerManager::class.java) ?: return
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "asr:upload_fg",
        ).also {
            it.setReferenceCounted(false)
            // EDGE: hard cap so a stuck upload cannot hold the lock forever.
            it.acquire(60 * 60 * 1000L)
        }
    }

    private fun releaseWakeLock() {
        try {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        } catch (_: Exception) {
        }
        wakeLock = null
    }

    override fun onDestroy() {
        releaseWakeLock()
        super.onDestroy()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java) ?: return
        val ch = NotificationChannel(
            CHANNEL_ID,
            "PDF 업로드",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "PDF를 올리고 처리하는 동안 표시됩니다."
        }
        nm.createNotificationChannel(ch)
        // design/105 — fail/result must be able to alert (not silent vanish).
        val result = NotificationChannel(
            RESULT_CHANNEL_ID,
            "PDF 업로드 결과",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "업로드 완료·실패를 알려 줍니다."
        }
        nm.createNotificationChannel(result)
    }

    private fun buildNotification(
        title: String,
        text: String,
        cacheId: String?,
    ): Notification {
        val launch = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            action = ACTION_OPEN_FROM_NOTIFY
            if (!cacheId.isNullOrBlank()) {
                putExtra(EXTRA_CACHE_ID, cacheId)
            }
        }
        val pi = PendingIntent.getActivity(
            this,
            0,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title.take(64))
            .setContentText(text.take(96))
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentIntent(pi)
            .setOnlyAlertOnce(true)
            .setOngoing(cacheId.isNullOrBlank())
            .setAutoCancel(!cacheId.isNullOrBlank())
            .build()
    }

    companion object {
        const val CHANNEL_ID = "asr_upload_progress"
        const val RESULT_CHANNEL_ID = "asr_upload_result"
        const val NOTIF_ID = 74101
        const val RESULT_NOTIF_ID = 74102
        const val ACTION_START = "com.gjtuc.sentence_reading.UPLOAD_FG_START"
        const val ACTION_UPDATE = "com.gjtuc.sentence_reading.UPLOAD_FG_UPDATE"
        const val ACTION_STOP = "com.gjtuc.sentence_reading.UPLOAD_FG_STOP"
        const val ACTION_FAIL = "com.gjtuc.sentence_reading.UPLOAD_FG_FAIL"
        const val ACTION_OPEN_FROM_NOTIFY = "com.gjtuc.sentence_reading.OPEN_FROM_UPLOAD_NOTIFY"
        const val EXTRA_TITLE = "title"
        const val EXTRA_TEXT = "text"
        const val EXTRA_CACHE_ID = "cache_id"

        fun start(ctx: Context, title: String, text: String) {
            val i = Intent(ctx, UploadForegroundService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_TEXT, text)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(i)
            } else {
                ctx.startService(i)
            }
        }

        fun update(ctx: Context, title: String, text: String, cacheId: String? = null) {
            val i = Intent(ctx, UploadForegroundService::class.java).apply {
                action = ACTION_UPDATE
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_TEXT, text)
                if (!cacheId.isNullOrBlank()) putExtra(EXTRA_CACHE_ID, cacheId)
            }
            ctx.startService(i)
        }

        fun stop(ctx: Context) {
            val i = Intent(ctx, UploadForegroundService::class.java).apply {
                action = ACTION_STOP
            }
            ctx.startService(i)
        }

        /**
         * design/105 — stop foreground progress and leave a dismissible fail notice.
         * WHY separate channel: progress is LOW (no heads-up); fail must be DEFAULT.
         */
        fun showFailed(ctx: Context, title: String, text: String) {
            val i = Intent(ctx, UploadForegroundService::class.java).apply {
                action = ACTION_FAIL
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_TEXT, text)
            }
            ctx.startService(i)
        }

        fun postFailedNotification(ctx: Context, title: String, text: String) {
            val app = ctx.applicationContext
            val nm = app.getSystemService(NotificationManager::class.java) ?: return
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val result = NotificationChannel(
                    RESULT_CHANNEL_ID,
                    "PDF 업로드 결과",
                    NotificationManager.IMPORTANCE_DEFAULT,
                ).apply {
                    description = "업로드 완료·실패를 알려 줍니다."
                }
                nm.createNotificationChannel(result)
            }
            val launch = Intent(app, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                action = ACTION_OPEN_FROM_NOTIFY
            }
            val pi = PendingIntent.getActivity(
                app,
                1,
                launch,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            val safeTitle = title.take(64).ifBlank { "업로드 실패" }
            val safeText = text.take(96).ifBlank { "처리에 실패했습니다." }
            val n = NotificationCompat.Builder(app, RESULT_CHANNEL_ID)
                .setContentTitle(safeTitle)
                .setContentText(safeText)
                .setSmallIcon(android.R.drawable.stat_notify_error)
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setOngoing(false)
                .build()
            nm.notify(RESULT_NOTIF_ID, n)
        }
    }
}
