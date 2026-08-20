#include <jni.h>

#include <algorithm>
#include <atomic>
#include <mutex>
#include <string>

#include "whisper.h"

namespace {

struct WhisperHandle {
    whisper_context * context;
    std::atomic_bool cancel_requested{false};
    std::mutex transcription_mutex;
};

void discard_upstream_log(ggml_log_level, const char *, void *) {
    // AppLogger owns the persistent, privacy-safe logs. Upstream INFO output
    // can contain the private model path, so it is intentionally suppressed.
}

void throw_java(JNIEnv * env, const char * class_name, const char * message) {
    jclass exception_class = env->FindClass(class_name);
    if (exception_class != nullptr) {
        env->ThrowNew(exception_class, message);
        env->DeleteLocalRef(exception_class);
    }
}

bool abort_requested(void * user_data) {
    auto * flag = static_cast<std::atomic_bool *>(user_data);
    return flag != nullptr && flag->load(std::memory_order_relaxed);
}

WhisperHandle * from_pointer(jlong pointer) {
    return reinterpret_cast<WhisperHandle *>(pointer);
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_com_smyongbu_voiceinput_WhisperAcftNative_create(
        JNIEnv * env,
        jclass,
        jstring model_path) {
    if (model_path == nullptr) {
        throw_java(env, "java/lang/IllegalArgumentException", "Whisper model path is missing");
        return 0;
    }

    static std::once_flag log_configuration;
    std::call_once(log_configuration, [] { whisper_log_set(discard_upstream_log, nullptr); });

    const char * path = env->GetStringUTFChars(model_path, nullptr);
    if (path == nullptr) return 0;

    whisper_context_params context_params = whisper_context_default_params();
    context_params.use_gpu = false;
    context_params.flash_attn = false;
    whisper_context * context = whisper_init_from_file_with_params(path, context_params);
    env->ReleaseStringUTFChars(model_path, path);

    if (context == nullptr) {
        throw_java(env, "java/lang/IllegalStateException", "Whisper model could not be loaded");
        return 0;
    }

    auto * handle = new WhisperHandle{context};
    return reinterpret_cast<jlong>(handle);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_smyongbu_voiceinput_WhisperAcftNative_transcribe(
        JNIEnv * env,
        jclass,
        jlong handle_pointer,
        jfloatArray audio,
        jint thread_count,
        jstring language_hint,
        jint audio_context) {
    WhisperHandle * handle = from_pointer(handle_pointer);
    if (handle == nullptr || handle->context == nullptr) {
        throw_java(env, "java/lang/IllegalStateException", "Whisper context is closed");
        return nullptr;
    }
    if (audio == nullptr) {
        throw_java(env, "java/lang/IllegalArgumentException", "Whisper audio is missing");
        return nullptr;
    }

    std::lock_guard<std::mutex> guard(handle->transcription_mutex);

    const jsize sample_count = env->GetArrayLength(audio);
    jfloat * samples = env->GetFloatArrayElements(audio, nullptr);
    if (samples == nullptr) return nullptr;

    const char * language = "auto";
    const char * acquired_language = nullptr;
    if (language_hint != nullptr) {
        acquired_language = env->GetStringUTFChars(language_hint, nullptr);
        if (acquired_language != nullptr && acquired_language[0] != '\0') language = acquired_language;
    }

    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.n_threads = std::clamp(static_cast<int>(thread_count), 1, 8);
    params.translate = false;
    params.no_context = true;
    params.no_timestamps = true;
    params.single_segment = false;
    params.print_special = false;
    params.print_progress = false;
    params.print_realtime = false;
    params.print_timestamps = false;
    params.language = language;
    params.audio_ctx = std::clamp(
            static_cast<int>(audio_context),
            1,
            whisper_model_n_audio_ctx(handle->context));
    params.abort_callback = abort_requested;
    params.abort_callback_user_data = &handle->cancel_requested;

    const int result = whisper_full(handle->context, params, samples, sample_count);

    if (acquired_language != nullptr) env->ReleaseStringUTFChars(language_hint, acquired_language);
    env->ReleaseFloatArrayElements(audio, samples, JNI_ABORT);

    if (handle->cancel_requested.load(std::memory_order_relaxed)) {
        throw_java(env, "java/util/concurrent/CancellationException", "Whisper transcription cancelled");
        return nullptr;
    }
    if (result != 0) {
        throw_java(env, "java/lang/IllegalStateException", "Whisper transcription failed");
        return nullptr;
    }

    std::string transcript;
    const int segment_count = whisper_full_n_segments(handle->context);
    for (int index = 0; index < segment_count; ++index) {
        const char * segment = whisper_full_get_segment_text(handle->context, index);
        if (segment != nullptr) transcript.append(segment);
    }
    return env->NewStringUTF(transcript.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_smyongbu_voiceinput_WhisperAcftNative_resetCancellation(
        JNIEnv *,
        jclass,
        jlong handle_pointer) {
    WhisperHandle * handle = from_pointer(handle_pointer);
    if (handle != nullptr) handle->cancel_requested.store(false, std::memory_order_relaxed);
}

extern "C" JNIEXPORT void JNICALL
Java_com_smyongbu_voiceinput_WhisperAcftNative_cancel(
        JNIEnv *,
        jclass,
        jlong handle_pointer) {
    WhisperHandle * handle = from_pointer(handle_pointer);
    if (handle != nullptr) handle->cancel_requested.store(true, std::memory_order_relaxed);
}

extern "C" JNIEXPORT void JNICALL
Java_com_smyongbu_voiceinput_WhisperAcftNative_destroy(
        JNIEnv *,
        jclass,
        jlong handle_pointer) {
    WhisperHandle * handle = from_pointer(handle_pointer);
    if (handle == nullptr) return;
    {
        std::lock_guard<std::mutex> guard(handle->transcription_mutex);
        if (handle->context != nullptr) {
            whisper_free(handle->context);
            handle->context = nullptr;
        }
    }
    delete handle;
}
