package com.smyongbu.voiceinput

import android.content.Context
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicLong

internal object WhisperAcftNative {
    init {
        System.loadLibrary("whisper_acft_jni")
    }

    @JvmStatic external fun create(modelPath: String): Long
    @JvmStatic external fun transcribe(
        handle: Long,
        samples: FloatArray,
        threadCount: Int,
        languageHint: String,
        audioContext: Int
    ): String
    @JvmStatic external fun resetCancellation(handle: Long)
    @JvmStatic external fun cancel(handle: Long)
    @JvmStatic external fun destroy(handle: Long)
}

internal class WhisperNativeHandle(initialHandle: Long) {
    @Volatile private var handle = initialHandle
    private val lifecycleLock = Any()

    fun current(): Long = handle

    fun withOpenHandle(block: (Long) -> Unit) {
        synchronized(lifecycleLock) {
            val currentHandle = handle
            if (currentHandle != 0L) block(currentHandle)
        }
    }

    fun detach(): Long = synchronized(lifecycleLock) {
        handle.also { handle = 0L }
    }
}

internal class WhisperCancellationGeneration {
    private val generation = AtomicLong(0)

    fun prepareForSession(reset: () -> Unit, reassertCancellation: () -> Unit) {
        val generationAtStart = generation.get()
        reset()
        if (generation.get() != generationAtStart) reassertCancellation()
    }

    fun markCancelled() {
        generation.incrementAndGet()
    }
}

class WhisperAcftRecognizer private constructor(
    private val logger: AppLogger,
    private val threadCount: Int,
    nativeHandle: Long
) : AutoCloseable {
    private val nativeHandle = WhisperNativeHandle(nativeHandle)
    private val cancellationGeneration = WhisperCancellationGeneration()

    @Synchronized
    fun prepareForSession() {
        val currentHandle = nativeHandle.current()
        check(currentHandle != 0L) { "Whisper ACFT 识别器已释放" }
        cancellationGeneration.prepareForSession(
            reset = { WhisperAcftNative.resetCancellation(currentHandle) },
            reassertCancellation = { WhisperAcftNative.cancel(currentHandle) }
        )
    }

    @Synchronized
    fun transcribe(samples: FloatArray, languageHint: String = "auto"): String {
        val currentHandle = nativeHandle.current()
        check(currentHandle != 0L) { "Whisper ACFT 识别器已释放" }
        if (samples.size < MINIMUM_TRANSCRIBABLE_SAMPLES) return ""

        val operationId = "whisper-${operationIds.incrementAndGet().toString(36)}"
        val startedAt = System.currentTimeMillis()
        val audioContext = calculateDynamicAudioContext(samples.size)
        logger.info(
            "Whisper ACFT 整段识别开始，采样=${samples.size}，音频上下文=$audioContext，线程=$threadCount",
            operationId
        )
        return try {
            val raw = WhisperAcftNative.transcribe(
                currentHandle,
                samples,
                threadCount,
                normalizeLanguageHint(languageHint),
                audioContext
            )
            cleanTranscript(raw).also { result ->
                logger.info(
                    "Whisper ACFT 整段识别完成，耗时=${System.currentTimeMillis() - startedAt}毫秒，字符=${result.length}",
                    operationId
                )
            }
        } catch (cancelled: CancellationException) {
            logger.info("Whisper ACFT 整段识别已取消", operationId)
            throw cancelled
        } catch (error: Throwable) {
            logger.error("Whisper ACFT 整段识别失败", error, operationId)
            throw error
        }
    }

    fun cancel() {
        cancellationGeneration.markCancelled()
        nativeHandle.withOpenHandle(WhisperAcftNative::cancel)
    }

    @Synchronized
    override fun close() {
        val currentHandle = nativeHandle.detach()
        if (currentHandle == 0L) return
        try {
            WhisperAcftNative.destroy(currentHandle)
            logger.info("Whisper ACFT 识别器已释放", "whisper-release")
        } catch (error: Throwable) {
            logger.error("Whisper ACFT 识别器释放失败", error, "whisper-release")
        }
    }

    companion object {
        const val RESOURCE_ID = "whisper-acft-multilingual-74"
        const val MODEL_FILE_NAME = "base_acft_q8_0.bin"
        const val SAMPLE_RATE = 16_000
        private const val SAMPLES_PER_AUDIO_CONTEXT = 320
        private const val MAXIMUM_AUDIO_CONTEXT = 1_500
        private const val MINIMUM_TRANSCRIBABLE_SAMPLES = SAMPLE_RATE / 10
        private val operationIds = AtomicLong(0)

        fun fromInstalledModel(
            context: Context,
            threadCount: Int = preferredThreadCount()
        ): WhisperAcftRecognizer {
            val app = context.applicationContext
            val logger = AppLogger(app)
            val operationId = "whisper-load-${System.currentTimeMillis().toString(36)}"
            ModelResourceManager.init(app)
            val modelPath = ModelResourceManager.modelPath(RESOURCE_ID, MODEL_FILE_NAME)
            logger.info("Whisper ACFT 模型开始加载，线程=${threadCount.coerceIn(1, 8)}", operationId)
            return try {
                val nativeHandle = WhisperAcftNative.create(modelPath)
                check(nativeHandle != 0L) { "Whisper ACFT 模型加载失败" }
                logger.info("Whisper ACFT 模型加载完成", operationId)
                WhisperAcftRecognizer(logger, threadCount.coerceIn(1, 8), nativeHandle)
            } catch (error: Throwable) {
                logger.error("Whisper ACFT 模型加载失败", error, operationId)
                throw IllegalStateException("Whisper ACFT 模型加载失败，请校验或重新下载模型。", error)
            }
        }

        fun preferredThreadCount(): Int =
            (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 4)

        internal fun calculateDynamicAudioContext(sampleCount: Int): Int {
            if (sampleCount <= 0) return 0
            return ((sampleCount + SAMPLES_PER_AUDIO_CONTEXT - 1) / SAMPLES_PER_AUDIO_CONTEXT)
                .coerceIn(1, MAXIMUM_AUDIO_CONTEXT)
        }

        internal fun normalizeLanguageHint(languageHint: String?): String =
            languageHint?.trim()?.lowercase()?.takeIf { it in setOf("auto", "zh", "en") } ?: "auto"

        internal fun cleanTranscript(text: String): String = text
            .replace(Regex("<\\|[^>]+\\|>"), " ")
            .replace(Regex("[\\t\\n\\r ]+"), " ")
            .trim()
    }
}
