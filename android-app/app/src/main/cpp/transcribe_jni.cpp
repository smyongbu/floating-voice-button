#include <jni.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

#include "transcribe.h"

namespace {

struct TranscribeHandle {
    transcribe_session * session = nullptr;
    std::atomic_bool cancel_requested{false};
    std::mutex transcription_mutex;
};

void throw_java(JNIEnv * env, const char * class_name, const std::string & message) {
    jclass exception_class = env->FindClass(class_name);
    if (exception_class != nullptr) {
        env->ThrowNew(exception_class, message.c_str());
        env->DeleteLocalRef(exception_class);
    }
}

bool abort_requested(void * user_data) {
    auto * flag = static_cast<std::atomic_bool *>(user_data);
    return flag != nullptr && flag->load(std::memory_order_relaxed);
}

TranscribeHandle * from_pointer(jlong pointer) {
    return reinterpret_cast<TranscribeHandle *>(pointer);
}

std::u16string utf8_to_utf16(const char * text) {
    std::u16string output;
    if (text == nullptr) return output;

    const auto * cursor = reinterpret_cast<const unsigned char *>(text);
    while (*cursor != 0) {
        uint32_t codepoint = 0xfffd;
        size_t length = 1;
        if (*cursor < 0x80) {
            codepoint = *cursor;
        } else if ((*cursor & 0xe0) == 0xc0 && cursor[1] != 0) {
            codepoint = ((*cursor & 0x1f) << 6) | (cursor[1] & 0x3f);
            length = codepoint >= 0x80 ? 2 : 1;
            if (length == 1) codepoint = 0xfffd;
        } else if (
            (*cursor & 0xf0) == 0xe0 &&
            cursor[1] != 0 &&
            cursor[2] != 0
        ) {
            codepoint = ((*cursor & 0x0f) << 12) |
                ((cursor[1] & 0x3f) << 6) |
                (cursor[2] & 0x3f);
            length = codepoint >= 0x800 ? 3 : 1;
            if (length == 1 || (codepoint >= 0xd800 && codepoint <= 0xdfff)) {
                codepoint = 0xfffd;
                length = 1;
            }
        } else if (
            (*cursor & 0xf8) == 0xf0 &&
            cursor[1] != 0 &&
            cursor[2] != 0 &&
            cursor[3] != 0
        ) {
            codepoint = ((*cursor & 0x07) << 18) |
                ((cursor[1] & 0x3f) << 12) |
                ((cursor[2] & 0x3f) << 6) |
                (cursor[3] & 0x3f);
            length = codepoint >= 0x10000 && codepoint <= 0x10ffff ? 4 : 1;
            if (length == 1) codepoint = 0xfffd;
        }
        if (codepoint <= 0xffff) {
            output.push_back(static_cast<char16_t>(codepoint));
        } else {
            codepoint -= 0x10000;
            output.push_back(static_cast<char16_t>(0xd800 + (codepoint >> 10)));
            output.push_back(static_cast<char16_t>(0xdc00 + (codepoint & 0x3ff)));
        }
        cursor += length;
    }
    return output;
}

jstring new_java_string(JNIEnv * env, const char * utf8) {
    const std::u16string text = utf8_to_utf16(utf8);
    return env->NewString(
        reinterpret_cast<const jchar *>(text.data()),
        static_cast<jsize>(text.size()));
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_com_smyongbu_voiceinput_TranscribeCppNative_create(
        JNIEnv * env,
        jclass,
        jstring model_path,
        jint thread_count) {
    if (model_path == nullptr) {
        throw_java(env, "java/lang/IllegalArgumentException", "Model path is missing");
        return 0;
    }

    static std::once_flag log_configuration;
    std::call_once(log_configuration, [] { transcribe_log_set(nullptr, nullptr); });

    const char * path = env->GetStringUTFChars(model_path, nullptr);
    if (path == nullptr) return 0;

    transcribe_session_params params;
    transcribe_session_params_init(&params);
    params.n_threads = std::clamp(static_cast<int>(thread_count), 1, 8);

    transcribe_session * session = nullptr;
    const transcribe_status status = transcribe_open(path, nullptr, &params, &session);
    env->ReleaseStringUTFChars(model_path, path);

    if (status != TRANSCRIBE_OK || session == nullptr) {
        const char * detail = transcribe_status_string(status);
        throw_java(
            env,
            "java/lang/IllegalStateException",
            std::string("Model could not be loaded: ") + (detail == nullptr ? "unknown" : detail));
        return 0;
    }

    auto * handle = new TranscribeHandle();
    handle->session = session;
    transcribe_set_abort_callback(session, abort_requested, &handle->cancel_requested);
    return reinterpret_cast<jlong>(handle);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_smyongbu_voiceinput_TranscribeCppNative_transcribe(
        JNIEnv * env,
        jclass,
        jlong handle_pointer,
        jfloatArray audio,
        jstring language_hint) {
    TranscribeHandle * handle = from_pointer(handle_pointer);
    if (handle == nullptr || handle->session == nullptr) {
        throw_java(env, "java/lang/IllegalStateException", "Transcribe session is closed");
        return nullptr;
    }
    if (audio == nullptr) {
        throw_java(env, "java/lang/IllegalArgumentException", "Audio is missing");
        return nullptr;
    }

    std::lock_guard<std::mutex> guard(handle->transcription_mutex);
    const jsize sample_count = env->GetArrayLength(audio);
    if (sample_count <= 0) return new_java_string(env, "");

    std::vector<float> samples(static_cast<size_t>(sample_count));
    env->GetFloatArrayRegion(audio, 0, sample_count, samples.data());
    if (env->ExceptionCheck()) return nullptr;

    const char * acquired_language = nullptr;
    if (language_hint != nullptr) {
        acquired_language = env->GetStringUTFChars(language_hint, nullptr);
        if (acquired_language == nullptr) return nullptr;
    }

    transcribe_run_params params;
    transcribe_run_params_init(&params);
    params.task = TRANSCRIBE_TASK_TRANSCRIBE;
    params.timestamps = TRANSCRIBE_TIMESTAMPS_NONE;
    params.language = acquired_language != nullptr && acquired_language[0] != '\0'
        ? acquired_language
        : nullptr;
    params.keep_special_tags = false;

    const transcribe_status status = transcribe_run(
        handle->session,
        samples.data(),
        static_cast<int>(sample_count),
        &params);

    if (acquired_language != nullptr) {
        env->ReleaseStringUTFChars(language_hint, acquired_language);
    }

    if (
        status == TRANSCRIBE_ERR_ABORTED ||
        handle->cancel_requested.load(std::memory_order_relaxed)
    ) {
        throw_java(
            env,
            "java/util/concurrent/CancellationException",
            "Transcription cancelled");
        return nullptr;
    }
    if (status != TRANSCRIBE_OK && status != TRANSCRIBE_ERR_OUTPUT_TRUNCATED) {
        const char * detail = transcribe_status_string(status);
        throw_java(
            env,
            "java/lang/IllegalStateException",
            std::string("Transcription failed: ") + (detail == nullptr ? "unknown" : detail));
        return nullptr;
    }

    return new_java_string(env, transcribe_full_text(handle->session));
}

extern "C" JNIEXPORT void JNICALL
Java_com_smyongbu_voiceinput_TranscribeCppNative_resetCancellation(
        JNIEnv *,
        jclass,
        jlong handle_pointer) {
    TranscribeHandle * handle = from_pointer(handle_pointer);
    if (handle != nullptr) {
        handle->cancel_requested.store(false, std::memory_order_relaxed);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_smyongbu_voiceinput_TranscribeCppNative_cancel(
        JNIEnv *,
        jclass,
        jlong handle_pointer) {
    TranscribeHandle * handle = from_pointer(handle_pointer);
    if (handle != nullptr) {
        handle->cancel_requested.store(true, std::memory_order_relaxed);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_smyongbu_voiceinput_TranscribeCppNative_destroy(
        JNIEnv *,
        jclass,
        jlong handle_pointer) {
    TranscribeHandle * handle = from_pointer(handle_pointer);
    if (handle == nullptr) return;
    {
        std::lock_guard<std::mutex> guard(handle->transcription_mutex);
        if (handle->session != nullptr) {
            transcribe_session_free(handle->session);
            handle->session = nullptr;
        }
    }
    delete handle;
}
