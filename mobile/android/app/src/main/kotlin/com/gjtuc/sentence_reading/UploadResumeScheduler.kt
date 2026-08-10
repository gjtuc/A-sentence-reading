package com.gjtuc.sentence_reading

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * design/76 — schedule unique WorkManager job for upload resume after process death.
 * INVARIANT: do not put session tokens in Work input data.
 */
object UploadResumeScheduler {
    const val UNIQUE_WORK = "asr_upload_resume_v1"

    fun schedule(context: Context, immediate: Boolean) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val builder = OneTimeWorkRequestBuilder<UploadResumeWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
        if (!immediate) {
            // WHY: give live Flutter upload time to keep progressing; fire if frozen/dead.
            builder.setInitialDelay(60, TimeUnit.SECONDS)
        }
        // WHY: REPLACE so progress heartbeats reset the delay; KEEP would leave a stale timer.
        WorkManager.getInstance(context.applicationContext)
            .enqueueUniqueWork(UNIQUE_WORK, ExistingWorkPolicy.REPLACE, builder.build())
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(UNIQUE_WORK)
    }
}
