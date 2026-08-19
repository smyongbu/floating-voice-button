plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val developmentKeystorePath = providers.environmentVariable("ANDROID_KEYSTORE_PATH").orNull
val developmentKeystorePassword = providers.environmentVariable("ANDROID_KEYSTORE_PASSWORD").orNull
val developmentKeyAlias = providers.environmentVariable("ANDROID_KEY_ALIAS").orNull
val developmentKeyPassword = providers.environmentVariable("ANDROID_KEY_PASSWORD").orNull
val hasDevelopmentSigning = listOf(
    developmentKeystorePath,
    developmentKeystorePassword,
    developmentKeyAlias,
    developmentKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "com.smyongbu.voiceinput"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.smyongbu.voiceinput"
        minSdk = 26
        targetSdk = 35
        versionCode = 15
        versionName = "0.10.2"
        ndk { abiFilters += "arm64-v8a" }
    }

    signingConfigs {
        if (hasDevelopmentSigning) {
            create("development") {
                storeFile = file(developmentKeystorePath!!)
                storePassword = developmentKeystorePassword
                keyAlias = developmentKeyAlias
                keyPassword = developmentKeyPassword
            }
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfigs.findByName("development")?.let { signingConfig = it }
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("com.github.k2-fsa:sherpa-onnx:v1.13.5") {
        exclude(group = "com.github.k2-fsa.sherpa-onnx", module = "sherpa-onnx-jvm")
    }
    implementation("androidx.core:core:1.16.0")
    implementation("androidx.webkit:webkit:1.16.0")
    testImplementation("junit:junit:4.13.2")
}
