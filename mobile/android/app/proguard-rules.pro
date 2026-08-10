# design/76 — WorkManager/Room must survive R8 if minify is re-enabled later.
-keep class androidx.work.** { *; }
-keep class androidx.work.impl.** { *; }
-keep class androidx.work.impl.WorkDatabase { *; }
-keep class androidx.work.impl.WorkDatabase_Impl { *; }
-keep class * extends androidx.work.Worker
-keep class * extends androidx.work.CoroutineWorker
-keep class * extends androidx.work.ListenableWorker {
    public <init>(android.content.Context,androidx.work.WorkerParameters);
}
-keep class * extends androidx.room.RoomDatabase
-keep class * extends androidx.room.RoomDatabase_Impl
-dontwarn androidx.work.**
-dontwarn androidx.room.**
