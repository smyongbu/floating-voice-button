package com.smyongbu.voiceinput

import android.content.Context
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicLong

internal object TranscribeCppNative {
    init {
        System.loadLibrary("transcribe_jni")
    }

    @JvmStatic external fun create(modelPath: String, threadCount: Int): Long
    @JvmStatic external fun transcribe(
        handle: Long,
        samples: FloatArray,
        languageHint: String,
    ): String
    @JvmStatic external fun resetCancellation(handle: Long)
    @JvmStatic external fun cancel(handle: Long)
    @JvmStatic external fun destroy(handle: Long)
}

internal data class TranscribeModelSpec(
    val wireValue: String,
    val resourceId: String,
    val fileName: String,
    val displayName: String,
)

internal class TranscribeNativeHandle(initialHandle: Long) {
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

internal class TranscribeCancellationGeneration {
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

internal class TranscribeCppRecognizer private constructor(
    private val logger: AppLogger,
    val model: TranscribeModelSpec,
    private val threadCount: Int,
    nativeHandle: Long,
) : AutoCloseable {
    private val nativeHandle = TranscribeNativeHandle(nativeHandle)
    private val cancellationGeneration = TranscribeCancellationGeneration()

    @Synchronized
    fun prepareForSession() {
        val currentHandle = nativeHandle.current()
        check(currentHandle != 0L) { "${model.displayName} 识别器已释放" }
        cancellationGeneration.prepareForSession(
            reset = { TranscribeCppNative.resetCancellation(currentHandle) },
            reassertCancellation = { TranscribeCppNative.cancel(currentHandle) },
        )
    }

    @Synchronized
    fun transcribe(samples: FloatArray, languageHint: String = "auto"): String {
        val currentHandle = nativeHandle.current()
        check(currentHandle != 0L) { "${model.displayName} 识别器已释放" }
        if (samples.size < MINIMUM_TRANSCRIBABLE_SAMPLES) return ""

        val operationId = "transcribe-${operationIds.incrementAndGet().toString(36)}"
        val startedAt = System.currentTimeMillis()
        logger.info(
            "${model.displayName} 最终识别开始，采样=${samples.size}，线程=$threadCount",
            operationId,
        )
        return try {
            TranscribeCppNative.transcribe(
                currentHandle,
                samples,
                normalizeLanguageHint(languageHint),
            ).let(::cleanTranscript).also { result ->
                logger.info(
                    "${model.displayName} 最终识别完成，耗时=${System.currentTimeMillis() - startedAt}毫秒，字符=${result.length}",
                    operationId,
                )
            }
        } catch (cancelled: CancellationException) {
            logger.info("${model.displayName} 最终识别已取消", operationId)
            throw cancelled
        } catch (error: Throwable) {
            logger.error("${model.displayName} 最终识别失败", error, operationId)
            throw error
        }
    }

    fun cancel() {
        cancellationGeneration.markCancelled()
        nativeHandle.withOpenHandle(TranscribeCppNative::cancel)
    }

    @Synchronized
    override fun close() {
        val currentHandle = nativeHandle.detach()
        if (currentHandle == 0L) return
        try {
            TranscribeCppNative.destroy(currentHandle)
            logger.info("${model.displayName} 识别器已释放", "transcribe-release")
        } catch (error: Throwable) {
            logger.error("${model.displayName} 识别器释放失败", error, "transcribe-release")
        }
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        private const val MINIMUM_TRANSCRIBABLE_SAMPLES = SAMPLE_RATE / 10
        private val operationIds = AtomicLong(0)

        internal fun specFor(finalModel: String): TranscribeModelSpec = when (finalModel) {
            RecognitionController.FINAL_FASTER_WHISPER_SMALL -> TranscribeModelSpec(
                wireValue = finalModel,
                resourceId = ModelResourceManager.FASTER_WHISPER_SMALL_ID,
                fileName = ModelResourceManager.FASTER_WHISPER_SMALL_FILE,
                displayName = "Faster-Whisper Small",
            )
            RecognitionController.FINAL_QWEN3_ASR_17B_Q5_K_M -> TranscribeModelSpec(
                wireValue = finalModel,
                resourceId = ModelResourceManager.QWEN_17B_ID,
                fileName = ModelResourceManager.QWEN_17B_FILE,
                displayName = "Qwen3-ASR 1.7B Q5_K_M",
            )
            else -> error("不支持的 transcribe.cpp 最终模型：$finalModel")
        }

        fun fromInstalledModel(
            context: Context,
            finalModel: String,
            threadCount: Int = preferredThreadCount(),
        ): TranscribeCppRecognizer {
            val app = context.applicationContext
            val logger = AppLogger(app)
            val spec = specFor(finalModel)
            val operationId = "transcribe-load-${System.currentTimeMillis().toString(36)}"
            ModelResourceManager.init(app)
            val modelPath = ModelResourceManager.modelPath(spec.resourceId, spec.fileName)
            val threads = threadCount.coerceIn(1, 8)
            logger.info("${spec.displayName} 模型开始加载，线程=$threads", operationId)
            return try {
                val nativeHandle = TranscribeCppNative.create(modelPath, threads)
                check(nativeHandle != 0L) { "${spec.displayName} 模型加载失败" }
                logger.info("${spec.displayName} 模型加载完成", operationId)
                TranscribeCppRecognizer(logger, spec, threads, nativeHandle)
            } catch (error: Throwable) {
                logger.error("${spec.displayName} 模型加载失败", error, operationId)
                throw IllegalStateException(
                    "${spec.displayName} 模型加载失败，请校验或重新下载模型。",
                    error,
                )
            }
        }

        fun preferredThreadCount(): Int =
            (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 4)

        internal fun normalizeLanguageHint(languageHint: String?): String =
            languageHint?.trim()?.lowercase()?.takeIf { it in setOf("zh", "en") }.orEmpty()

        internal fun cleanTranscript(text: String): String = text
            .replace(Regex("<\\|[^>]+\\|>"), " ")
            .replace(Regex("[\\t\\n\\r ]+"), " ")
            .trim()
    }
}
