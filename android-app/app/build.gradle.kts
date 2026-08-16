plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.smyongbu.voiceinput"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.smyongbu.voiceinput"
        minSdk = 26
        targetSdk = 35
        versionCode = 6
        versionName = "0.6.0"
        ndk { abiFilters += "arm64-v8a" }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += listOf("onnx", "txt", "model") }
}

dependencies {
    implementation("com.github.k2-fsa:sherpa-onnx:v1.13.4")
    testImplementation("junit:junit:4.13.2")
}
