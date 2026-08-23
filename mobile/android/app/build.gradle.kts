import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
    // Firebase: reads google-services.json to configure FCM at build time.
    id("com.google.gms.google-services")
}

// Optional release signing: CI writes android/key.properties from secrets when a
// keystore is configured. When it's absent (local dev, or no secrets set) the
// release build falls back to debug signing so `flutter build` still works.
val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
val hasReleaseKeystore = keystorePropertiesFile.exists()
if (hasReleaseKeystore) {
    keystoreProperties.load(keystorePropertiesFile.inputStream())
}

android {
    namespace = "dev.allanweber.job_scalper"
    // Pinned explicitly (not `flutter.compileSdkVersion`) so the SDK the app
    // compiles and targets can't drift with a Flutter upgrade — Play rejects a
    // submission whose targetSdk is below its current floor, so this value is
    // release-critical and shouldn't move by accident. Keep compileSdk == targetSdk.
    compileSdk = 35
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "dev.allanweber.job_scalper"
        // google_sign_in_android (Credential Manager) requires API 24+.
        minSdk = maxOf(flutter.minSdkVersion, 24)
        // Pinned, not inherited from Flutter. Play's minimum target API rises
        // roughly once a year (API 35 / Android 15 was the 2025 floor for new
        // apps); confirm the current requirement in Play Console at submission
        // and bump this — and compileSdk above — together when it moves.
        targetSdk = 35
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Use the upload keystore when CI provides one; otherwise fall back to
            // debug signing so local `flutter build`/`run --release` still works.
            signingConfig = if (hasReleaseKeystore) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
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
