plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.gjtuc.sentence_reading"
    // WHY: file_picker + flutter_plugin_android_lifecycle require compileSdk ≥ 35 (design/70).
    compileSdk = maxOf(36, flutter.compileSdkVersion)
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // WHY: locked in design/33 — must stay com.gjtuc.sentence_reading (contract tests).
        applicationId = "com.gjtuc.sentence_reading"
        // Flutter Gradle Plugin supplies SDK floors from the installed Flutter SDK.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // Sideload MVP: debug signing until a release keystore exists (Play Store out of scope).
            signingConfig = signingConfigs.getByName("debug")
            // WHY: keep release non-minified for sideload parity with 0.2.91/0.2.92.
            // WorkManager+R8 previously crashed at InitializationProvider (WorkDatabase).
            // Proguard rules remain for when minify is turned on later.
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // WHY (design/74): NotificationCompat + ContextCompat for FG upload notify.
    implementation("androidx.core:core-ktx:1.13.1")
    // WHY (design/76): process-death resume without a new Flutter pub package.
    implementation("androidx.work:work-runtime-ktx:2.9.1")
}
