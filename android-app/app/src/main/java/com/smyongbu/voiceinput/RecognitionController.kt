package com.smyongbu.voiceinput

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineQwen3AsrModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineParaformerModelConfig
import com.k2fsa.sherpa.onnx.OnlineRecognizer
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineStream
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig
import java.util.ArrayDeque
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

object RecognitionController {
    const val REALTIME_STREAMING_PARAFORMER = "streaming_paraformer"
    const val REALTIME_ZIPFORMER = "zipformer"
    const val FINAL_FASTER_WHISPER_SMALL = "faster_whisper_small"
    const val FINAL_QWEN3_ASR_06B_INT8 = "qwen3_asr_06b_int8"
    const val FINAL_QWEN3_ASR_17B_Q5_K_M = "qwen3_asr_17b_q5_k_m"
    val validRealtimeModels = setOf(
        REALTIME_STREAMING_PARAFORMER,
        REALTIME_ZIPFORMER,
    )
    val validFinalModels = setOf(
        FINAL_FASTER_WHISPER_SMALL,
        FINAL_QWEN3_ASR_06B_INT8,
        FINAL_QWEN3_ASR_17B_Q5_K_M,
    )
    private const val KEY_REALTIME_MODEL = "realtime_model"
    private const val KEY_FINAL_MODEL = "final_model"
    private const val KEY_LEGACY_ENGINE = "engine"
    private const val DEFAULT_REALTIME_MODEL = REALTIME_STREAMING_PARAFORMER
    private const val DEFAULT_FINAL_MODEL = FINAL_QWEN3_ASR_17B_Q5_K_M

    // 旧版网页与设置迁移仍会传这些值；新界面只使用上面的两组 wire value。
    const val ENGINE_DUAL = "local_dual"
    const val ENGINE_DUAL_QWEN = "local_dual_qwen"
    const val ENGINE_DUAL_WHISPER = "local_dual_whisper_acft"
    const val ENGINE_ZIPFORMER = "local_zipformer"
    const val ENGINE_PARAFORMER = "local_paraformer"
    const val ENGINE_QWEN = "local_qwen"
    const val ENGINE_WHISPER = "local_whisper_acft"
    const val ENGINE_SYSTEM = "system"
    val validEngines = setOf(
        ENGINE_DUAL,
        ENGINE_DUAL_QWEN,
        ENGINE_DUAL_WHISPER,
        ENGINE_ZIPFORMER,
        ENGINE_PARAFORMER,
        ENGINE_QWEN,
        ENGINE_WHISPER,
        ENGINE_SYSTEM,
    )

    interface Listener {
        fun onRecognitionState(listening: Boolean, status: String, text: String)
        fun onAudioLevel(level: Float) = Unit
    }

    data class StateSnapshot(
        val active: Boolean,
        val capturing: Boolean,
        val phase: String,
        val status: String,
        val text: String,
        val finalProcessing: Boolean,
        val finalQueueCount: Int,
        val finalText: String,
    )

    data class PendingHistorySnapshot(
        val id: Long,
        val text: String,
        val createdAt: Long,
        val engine: String,
        val queueStatus: String,
    )

    private class Session(
        val id: Long,
        val realtimeModel: String,
        val finalModel: String,
        val testModeEnabled: Boolean,
    ) {
        val engine = "$realtimeModel+$finalModel"
        val createdAt = System.currentTimeMillis()
        val cancelled = AtomicBoolean(false)
        val finished = AtomicBoolean(false)
        val running = AtomicBoolean(true)
        val stopRequested = AtomicBoolean(false)
        @Volatile var text = ""
        @Volatile var recognizer: SpeechRecognizer? = null
        @Volatile var retry: Runnable? = null
        @Volatile var systemAttempt = 0
        @Volatile var systemRetry = 0
        @Volatile var captureStartedAt = 0L
        @Volatile var firstResultAt = 0L
        @Volatile var recordedSamples = 0
        @Volatile var resultUpdates = 0
        @Volatile var endpointCount = 0
    }

    private data class TestCapture(
        val realtimeDraft: String,
        val secondPassText: String?,
        val selectedResult: TestSelectedResult,
        val audioSamples: FloatArray,
    )

    private data class FinalJob(
        val session: Session,
        val realtime: String,
        val correctionSegments: List<FloatArray>,
        val wholeAudio: FloatArray,
        val correctionResourceId: String?,
        val useTranscribe: Boolean,
    )

    private val listeners = CopyOnWriteArrayList<Listener>()
    private val main = Handler(Looper.getMainLooper())
    private val stateLock = Any()
    private val sessionIds = AtomicLong(0)
    private val preloadRequests = AtomicLong(0)
    private val preloadStarted = AtomicBoolean(false)
    private val preloadPending = AtomicBoolean(false)
    private val localWorkerActive = AtomicBoolean(false)
    private val finalWorkerActive = AtomicBoolean(false)
    private val finalQueueLock = Any()
    private val finalQueue = ArrayDeque<FinalJob>()
    private val modelLock = Any()
    private val pendingModelReloads = ConcurrentHashMap.newKeySet<String>()
    private lateinit var app: Context
    private lateinit var logger: AppLogger
    private lateinit var history: HistoryStore
    @Volatile private var activeSession: Session? = null
    @Volatile private var processingFinalJob: FinalJob? = null
    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var cachedOnline: OnlineRecognizer? = null
    @Volatile private var cachedOnlineResourceId: String? = null
    @Volatile private var cachedOffline: OfflineRecognizer? = null
    @Volatile private var cachedOfflineResourceId: String? = null
    @Volatile private var cachedTranscribe: TranscribeCppRecognizer? = null
    @Volatile private var modelStatus = "正在检查本地模型…"
    @Volatile private var listening = false
    @Volatile private var lastText = ""
    @Volatile private var lastFinalText = ""
    @Volatile private var currentStatus = "正在检查本地模型…"
    @Volatile private var currentPhase = "idle"

    fun init(context: Context) {
        if (!::app.isInitialized) {
            app = context.applicationContext
            logger = AppLogger(app)
            history = HistoryStore(app)
            ModelResourceManager.init(app)
            migrateLegacySettings()
            preloadModels()
        }
    }

    fun addListener(listener: Listener) {
        listeners += listener
        listener.onRecognitionState(listening, currentStatus, lastText)
    }

    fun removeListener(listener: Listener) { listeners -= listener }

    fun selectedRealtimeModel(): String = app.getSharedPreferences("settings", 0)
        .getString(KEY_REALTIME_MODEL, DEFAULT_REALTIME_MODEL)
        .let { if (it in validRealtimeModels) it!! else DEFAULT_REALTIME_MODEL }

    fun selectedFinalModel(): String = app.getSharedPreferences("settings", 0)
        .getString(KEY_FINAL_MODEL, DEFAULT_FINAL_MODEL)
        .let { if (it in validFinalModels) it!! else DEFAULT_FINAL_MODEL }

    fun selectedEngine(): String = "${selectedRealtimeModel()}+${selectedFinalModel()}"

    fun setRealtimeModel(model: String) {
        updateModelSelection(
            realtimeModel = model.takeIf { it in validRealtimeModels } ?: DEFAULT_REALTIME_MODEL,
            finalModel = selectedFinalModel(),
        )
    }

    fun setFinalModel(model: String) {
        updateModelSelection(
            realtimeModel = selectedRealtimeModel(),
            finalModel = model.takeIf { it in validFinalModels } ?: DEFAULT_FINAL_MODEL,
        )
    }

    fun setEngine(engine: String) {
        val selection = legacySelection(engine)
        updateModelSelection(selection.first, selection.second)
    }

    private fun updateModelSelection(realtimeModel: String, finalModel: String) {
        app.getSharedPreferences("settings", 0).edit()
            .putString(KEY_REALTIME_MODEL, realtimeModel)
            .putString(KEY_FINAL_MODEL, finalModel)
            .putString(KEY_LEGACY_ENGINE, "$realtimeModel+$finalModel")
            .apply()
        if (modelWorkerBusy()) {
            preloadPending.set(true)
            preloadRequests.incrementAndGet()
        } else {
            preloadModels()
        }
    }

    private fun migrateLegacySettings() {
        val preferences = app.getSharedPreferences("settings", 0)
        val savedRealtime = preferences.getString(KEY_REALTIME_MODEL, null)
            ?.takeIf { it in validRealtimeModels }
        val savedFinal = preferences.getString(KEY_FINAL_MODEL, null)
            ?.takeIf { it in validFinalModels }
        if (savedRealtime != null && savedFinal != null) return

        val migrated = legacySelection(preferences.getString(KEY_LEGACY_ENGINE, null))
        preferences.edit()
            .putString(KEY_REALTIME_MODEL, savedRealtime ?: migrated.first)
            .putString(KEY_FINAL_MODEL, savedFinal ?: migrated.second)
            .putString(
                KEY_LEGACY_ENGINE,
                "${savedRealtime ?: migrated.first}+${savedFinal ?: migrated.second}",
            )
            .apply()
    }

    private fun legacySelection(engine: String?): Pair<String, String> {
        val combined = engine?.split("+", limit = 2)
        if (
            combined?.size == 2 &&
            combined[0] in validRealtimeModels &&
            combined[1] in validFinalModels
        ) {
            return combined[0] to combined[1]
        }
        return when (engine) {
            ENGINE_DUAL_QWEN, ENGINE_QWEN ->
                REALTIME_ZIPFORMER to FINAL_QWEN3_ASR_06B_INT8
            ENGINE_DUAL, ENGINE_DUAL_WHISPER, ENGINE_ZIPFORMER,
            ENGINE_PARAFORMER, ENGINE_WHISPER, "local" ->
                REALTIME_ZIPFORMER to FINAL_FASTER_WHISPER_SMALL
            else -> DEFAULT_REALTIME_MODEL to DEFAULT_FINAL_MODEL
        }
    }

    fun isListening() = activeSession?.finished?.get() == false

    fun isBusy() = isListening() || finalWorkerActive.get() || synchronized(finalQueueLock) {
        finalQueue.isNotEmpty()
    }

    private fun modelWorkerBusy(): Boolean =
        activeSession != null || localWorkerActive.get() || finalWorkerActive.get() ||
            synchronized(finalQueueLock) { finalQueue.isNotEmpty() }

    fun snapshot(): StateSnapshot {
        val queued = synchronized(finalQueueLock) { finalQueue.size }
        return StateSnapshot(
            active = isListening(),
            capturing = listening,
            phase = currentPhase,
            status = currentStatus,
            text = lastText,
            finalProcessing = processingFinalJob != null,
            finalQueueCount = queued,
            finalText = lastFinalText,
        )
    }

    fun pendingHistory(): List<PendingHistorySnapshot> {
        val processing = processingFinalJob
        val queued = synchronized(finalQueueLock) { finalQueue.toList() }
        return buildList {
            processing?.let { add(it.toPendingHistory("processing")) }
            queued.forEach { add(it.toPendingHistory("queued")) }
        }
    }

    private fun FinalJob.toPendingHistory(status: String) = PendingHistorySnapshot(
        id = -session.id,
        text = realtime.ifBlank { "等待生成最终文字" },
        createdAt = session.createdAt,
        engine = session.engine,
        queueStatus = status,
    )

    fun toggle() { if (isListening()) stop() else start() }

    fun start() {
        if (app.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            logger.warning("识别启动被拒绝：缺少麦克风权限", "recognition-permission")
            publishIdle("没有麦克风权限，请在主界面授权。")
            return
        }
        val realtimeModel = selectedRealtimeModel()
        val finalModel = selectedFinalModel()
        val engine = "$realtimeModel+$finalModel"
        val missing = requiredResources(realtimeModel, finalModel)
            .filterNot(ModelResourceManager::isInstalled)
        if (missing.isNotEmpty()) {
            logger.warning("识别启动被拒绝：模型资源未安装，方式=$engine", "recognition-resource")
            publishIdle("所选方案的模型尚未安装，请先到设置页下载。")
            return
        }
        val session = synchronized(stateLock) {
            if (activeSession != null || localWorkerActive.get()) null
            else Session(
                sessionIds.incrementAndGet(),
                realtimeModel,
                finalModel,
                RecognitionTestMode.isEnabled(app),
            ).also {
                activeSession = it
                listening = false
                lastText = ""
                currentPhase = "preparing"
                currentStatus = "正在准备识别…"
            }
        } ?: return
        preloadRequests.incrementAndGet()
        preloadPending.set(true)
        logger.info("识别会话开始，方式=${session.engine}", operationId(session))
        publish(session, false, "正在准备识别…", "", "preparing")
        publishLevel(session, 0f)
        startLocal(session)
    }

    fun stop() {
        val session = activeSession ?: return
        if (session.finished.get()) return
        session.running.set(false)
        publish(session, false, "正在使用最终模型整理文字…", session.text, "processing")
    }

    fun cancel() {
        val session = activeSession ?: return
        if (session.finished.get()) return
        session.cancelled.set(true)
        session.running.set(false)
        logger.info("请求取消识别，方式=${session.engine}")
        publish(session, false, "正在取消本次识别…", session.text, "processing")
    }

    private fun preloadModels() {
        preloadPending.set(false)
        val requestId = preloadRequests.incrementAndGet()
        if (modelWorkerBusy()) {
            preloadPending.set(true)
            return
        }
        if (!preloadStarted.compareAndSet(false, true)) {
            preloadPending.set(true)
            return
        }
        Thread({
            val started = System.currentTimeMillis()
            try {
                val realtimeModel = selectedRealtimeModel()
                val finalModel = selectedFinalModel()
                val engine = "$realtimeModel+$finalModel"
                val required = requiredResources(realtimeModel, finalModel).toSet()
                val missing = required.filterNot(ModelResourceManager::isInstalled)
                val onlineResourceId = realtimeResource(realtimeModel)
                val hasOnline = onlineResourceId in required &&
                    ModelResourceManager.isInstalled(onlineResourceId)
                val correctionId = correctionResource(finalModel)
                val hasOffline = correctionId != null && ModelResourceManager.isInstalled(correctionId)
                val transcribeId = transcribeResource(finalModel)
                val hasTranscribe = transcribeId != null &&
                    ModelResourceManager.isInstalled(transcribeId)

                if (required.isNotEmpty() && missing.isEmpty() && canApplyPreload(requestId)) {
                    modelStatus = "正在预加载已安装的本地模型…"
                    currentStatus = modelStatus
                    notifyModelStatus()
                }

                val applied = synchronized(modelLock) {
                    if (!canApplyPreload(requestId)) {
                        false
                    } else {
                        releaseUnusedRecognizers(required)
                        if (missing.isEmpty()) {
                            if (hasOnline) getOnlineRecognizer(realtimeModel)
                            if (hasOffline) getOfflineRecognizer(correctionId!!)
                            if (hasTranscribe) getTranscribeRecognizer(finalModel)
                        }
                        true
                    }
                }
                if (!applied || !canApplyPreload(requestId)) return@Thread

                modelStatus = when {
                    missing.isNotEmpty() -> "请到设置页下载所需的离线模型"
                    hasOnline && (hasOffline || hasTranscribe) -> "实时显示与最终识别模型已就绪"
                    else -> "已安装的本地模型准备就绪"
                }
                currentStatus = modelStatus
                notifyModelStatus()
                logger.info(
                    "本地模型预加载完成，方式=$engine，耗时=${System.currentTimeMillis() - started}毫秒",
                    "model-preload",
                )
            } catch (e: Throwable) {
                if (e is ThreadDeath) throw e
                if (canApplyPreload(requestId)) {
                    modelStatus = "本地模型加载失败，请校验或重新下载模型"
                    currentStatus = modelStatus
                    notifyModelStatus()
                    logger.error("本地模型预加载失败", e, "model-preload")
                } else {
                    logger.info("忽略已过期的模型预加载结果", "model-preload")
                }
            } finally {
                preloadStarted.set(false)
                if (
                    activeSession == null &&
                    !localWorkerActive.get() &&
                    preloadPending.compareAndSet(true, false)
                ) {
                    preloadModels()
                }
            }
        }, "本地模型预加载").start()
    }

    private fun canApplyPreload(requestId: Long): Boolean =
        requestId == preloadRequests.get() && activeSession == null && !localWorkerActive.get()

    private fun releaseUnusedRecognizers(required: Set<String>) {
        synchronized(modelLock) {
            if (cachedOnlineResourceId !in required) {
                runCatching { cachedOnline?.release() }
                cachedOnline = null
                cachedOnlineResourceId = null
            }
            if (cachedOfflineResourceId !in required) {
                runCatching { cachedOffline?.release() }
                cachedOffline = null
                cachedOfflineResourceId = null
            }
            if (cachedTranscribe?.model?.resourceId !in required) {
                runCatching { cachedTranscribe?.cancel() }
                runCatching { cachedTranscribe?.close() }
                cachedTranscribe = null
            }
        }
    }

    fun refreshModels() = preloadModels()

    fun refreshModel(id: String) {
        if (id !in ModelResourceManager.RECOGNITION_RESOURCE_IDS) return
        if (modelWorkerBusy()) {
            pendingModelReloads += id
            logger.info("模型已更新，将在当前识别结束后重新加载，资源=$id", "model-reload")
            return
        }
        if (unloadModel(id)) {
            preloadModels()
        } else {
            pendingModelReloads += id
        }
    }

    fun unloadModel(id: String): Boolean {
        if (modelWorkerBusy()) return false
        preloadRequests.incrementAndGet()
        synchronized(modelLock) {
            if (modelWorkerBusy()) return false
            when (id) {
                ModelResourceManager.STREAMING_PARAFORMER_ID,
                ModelResourceManager.ZIPFORMER_ID -> {
                    if (cachedOnlineResourceId == id) {
                        runCatching { cachedOnline?.release() }
                        cachedOnline = null
                        cachedOnlineResourceId = null
                    }
                }
                ModelResourceManager.QWEN_06B_ID -> {
                    runCatching { cachedOffline?.release() }
                    cachedOffline = null
                    cachedOfflineResourceId = null
                }
                ModelResourceManager.FASTER_WHISPER_SMALL_ID,
                ModelResourceManager.QWEN_17B_ID -> {
                    if (cachedTranscribe?.model?.resourceId == id) {
                        runCatching { cachedTranscribe?.cancel() }
                        runCatching { cachedTranscribe?.close() }
                        cachedTranscribe = null
                    }
                }
                else -> return false
            }
        }
        modelStatus = "模型资源状态已更新"
        currentStatus = modelStatus
        notifyModelStatus()
        return true
    }

    private fun drainPendingModelReloadsIfIdle() {
        if (modelWorkerBusy()) return
        pendingModelReloads.toList().forEach { id ->
            if (pendingModelReloads.remove(id)) refreshModel(id)
        }
    }

    private fun notifyModelStatus() = main.post {
        if (activeSession == null) listeners.forEach { it.onRecognitionState(false, modelStatus, lastText) }
    }

    private fun getOnlineRecognizer(realtimeModel: String): OnlineRecognizer {
        synchronized(modelLock) {
            val resourceId = realtimeResource(realtimeModel)
            cachedOnline?.takeIf { cachedOnlineResourceId == resourceId }?.let { return it }
            runCatching { cachedOnline?.release() }
            cachedOnline = null
            cachedOnlineResourceId = null
            val dir = ModelResourceManager.bundleDirectory(resourceId).absolutePath
            val modelConfig = if (realtimeModel == REALTIME_STREAMING_PARAFORMER) {
                OnlineModelConfig(
                    paraformer = OnlineParaformerModelConfig(
                        encoder = "$dir/encoder.int8.onnx",
                        decoder = "$dir/decoder.int8.onnx",
                    ),
                    tokens = "$dir/tokens.txt",
                    numThreads = 2,
                    provider = "cpu",
                    modelType = "paraformer",
                )
            } else {
                OnlineModelConfig(
                    transducer = OnlineTransducerModelConfig(
                        encoder = "$dir/encoder-epoch-99-avg-1.int8.onnx",
                        decoder = "$dir/decoder-epoch-99-avg-1.onnx",
                        joiner = "$dir/joiner-epoch-99-avg-1.int8.onnx",
                    ),
                    tokens = "$dir/tokens.txt",
                    numThreads = 2,
                    provider = "cpu",
                )
            }
            return OnlineRecognizer(
                config = OnlineRecognizerConfig(
                    modelConfig = modelConfig,
                    enableEndpoint = true,
                    decodingMethod = if (realtimeModel == REALTIME_ZIPFORMER) {
                        "modified_beam_search"
                    } else {
                        "greedy_search"
                    },
                    maxActivePaths = 4
                )
            ).also {
                cachedOnline = it
                cachedOnlineResourceId = resourceId
            }
        }
    }

    private fun getOfflineRecognizer(resourceId: String): OfflineRecognizer {
        synchronized(modelLock) {
            cachedOffline?.takeIf { cachedOfflineResourceId == resourceId }?.let { return it }
            runCatching { cachedOffline?.release() }
            cachedOffline = null
            cachedOfflineResourceId = null
            val dir = ModelResourceManager.bundleDirectory(resourceId).absolutePath
            check(resourceId == ModelResourceManager.QWEN_06B_ID) {
                "不支持的 sherpa-onnx 最终模型：$resourceId"
            }
            val modelConfig = OfflineModelConfig(
                qwen3Asr = OfflineQwen3AsrModelConfig(
                    convFrontend = "$dir/conv_frontend.onnx",
                    encoder = "$dir/encoder.int8.onnx",
                    decoder = "$dir/decoder.int8.onnx",
                    tokenizer = "$dir/tokenizer"
                ),
                tokens = "",
                numThreads = 3,
                provider = "cpu"
            )
            return OfflineRecognizer(
                config = OfflineRecognizerConfig(
                    modelConfig = modelConfig
                )
            ).also {
                cachedOffline = it
                cachedOfflineResourceId = resourceId
            }
        }
    }

    private fun getTranscribeRecognizer(finalModel: String): TranscribeCppRecognizer {
        synchronized(modelLock) {
            cachedTranscribe?.takeIf { it.model.wireValue == finalModel }?.let { return it }
            runCatching { cachedTranscribe?.cancel() }
            runCatching { cachedTranscribe?.close() }
            cachedTranscribe = null
            return TranscribeCppRecognizer.fromInstalledModel(app, finalModel)
                .also { cachedTranscribe = it }
        }
    }

    private fun realtimeResource(realtimeModel: String): String =
        if (realtimeModel == REALTIME_ZIPFORMER) {
            ModelResourceManager.ZIPFORMER_ID
        } else {
            ModelResourceManager.STREAMING_PARAFORMER_ID
        }

    private fun finalResource(finalModel: String): String = when (finalModel) {
        FINAL_FASTER_WHISPER_SMALL -> ModelResourceManager.FASTER_WHISPER_SMALL_ID
        FINAL_QWEN3_ASR_06B_INT8 -> ModelResourceManager.QWEN_06B_ID
        FINAL_QWEN3_ASR_17B_Q5_K_M -> ModelResourceManager.QWEN_17B_ID
        else -> ModelResourceManager.QWEN_17B_ID
    }

    private fun requiredResources(realtimeModel: String, finalModel: String): List<String> =
        listOf(realtimeResource(realtimeModel), finalResource(finalModel))

    private fun correctionResource(finalModel: String): String? = when (finalModel) {
        FINAL_QWEN3_ASR_06B_INT8 -> ModelResourceManager.QWEN_06B_ID
        else -> null
    }

    private fun transcribeResource(finalModel: String): String? = when (finalModel) {
        FINAL_FASTER_WHISPER_SMALL -> ModelResourceManager.FASTER_WHISPER_SMALL_ID
        FINAL_QWEN3_ASR_17B_Q5_K_M -> ModelResourceManager.QWEN_17B_ID
        else -> null
    }

    private fun isCurrent(session: Session, attempt: Int? = null): Boolean {
        return activeSession === session && !session.finished.get() &&
            (attempt == null || session.systemAttempt == attempt)
    }

    private fun startSystem(session: Session) = main.post {
        if (!isCurrent(session) || session.cancelled.get()) return@post
        try {
            runCatching { session.recognizer?.cancel() }
            runCatching { session.recognizer?.destroy() }
            val attempt = session.systemAttempt + 1
            session.systemAttempt = attempt
            val speech = SpeechRecognizer.createSpeechRecognizer(app)
            session.recognizer = speech
            speech.setRecognitionListener(systemListener(session, attempt))
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, app.packageName)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1800L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1200L)
            }
            publish(session, false, "正在连接系统识别服务…", "", "preparing")
            speech.startListening(intent)
            logger.info("启动系统默认识别")
        } catch (e: Exception) {
            logger.error("系统识别启动失败", e)
            finish(session, "系统识别启动失败，请改用本地识别。", session.text, false)
        }
    }

    private fun systemListener(session: Session, attempt: Int) = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            if (isCurrent(session, attempt) && !session.cancelled.get()) {
                if (session.captureStartedAt == 0L) {
                    session.captureStartedAt = System.currentTimeMillis()
                    logger.info("系统识别服务已开始收音", operationId(session))
                }
                publish(session, true, "请开始说话", session.text, "listening")
            }
        }

        override fun onBeginningOfSpeech() {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publish(session, true, "正在系统识别…", session.text, "listening")
        }

        override fun onRmsChanged(rmsdB: Float) {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publishLevel(session, ((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
        }

        override fun onBufferReceived(buffer: ByteArray?) = Unit

        override fun onEndOfSpeech() {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publish(session, false, "正在整理文字…", session.text, "processing")
        }

        override fun onPartialResults(results: Bundle?) {
            if (!isCurrent(session, attempt) || session.cancelled.get()) return
            first(results).takeIf { it.isNotBlank() }?.let {
                val preview = RecognitionText.formatRealtime(it)
                session.text = preview
                markResultUpdate(session)
                publish(session, true, "正在系统实时识别…", preview, "listening")
            }
        }

        override fun onResults(results: Bundle?) {
            if (!isCurrent(session, attempt) || session.cancelled.get()) return
            val text = first(results).ifBlank { session.text }
            if (text.isNotBlank() && session.firstResultAt == 0L) markResultUpdate(session)
            finish(session, if (text.isBlank()) "没有识别到文字。" else "系统识别完成", text, text.isNotBlank())
        }

        override fun onError(error: Int) { handleSystemError(session, attempt, error) }
        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    private fun handleSystemError(session: Session, attempt: Int, error: Int) {
        if (!isCurrent(session, attempt) || session.cancelled.get()) return
        if (session.stopRequested.get()) {
            finish(
                session,
                if (session.text.isBlank()) "系统识别已停止，没有可保存的文字。" else "系统识别完成",
                session.text,
                session.text.isNotBlank()
            )
            return
        }
        logger.error("系统识别失败，错误编号=$error")
        if (session.systemRetry < 1 &&
            (error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY || error == SpeechRecognizer.ERROR_CLIENT)
        ) {
            session.systemRetry++
            session.systemAttempt++
            runCatching { session.recognizer?.cancel() }
            runCatching { session.recognizer?.destroy() }
            session.recognizer = null
            val retry = Runnable {
                session.retry = null
                if (isCurrent(session) && !session.cancelled.get()) startSystem(session)
            }
            session.retry = retry
            main.postDelayed(retry, 450)
            return
        }
        val message = when (error) {
            SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
                "系统识别网络不可用，建议切换本地识别。"
            SpeechRecognizer.ERROR_NO_MATCH -> "系统没有听清，建议切换本地识别。"
            SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "没有检测到说话声音。"
            SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "系统识别服务正忙。"
            else -> "系统识别失败（错误 $error），建议使用本地识别。"
        }
        finish(session, message, session.text, false)
    }

    @Suppress("MissingPermission")
    private fun startLocal(session: Session) {
        if (!localWorkerActive.compareAndSet(false, true)) {
            finish(session, "本地识别正在结束，请稍后再试。", "", false)
            return
        }
        val engine = session.engine
        val correctionId = correctionResource(session.finalModel)
        val useTranscribe = transcribeResource(session.finalModel) != null
        val useWholeAudioFinal = session.finalModel == FINAL_FASTER_WHISPER_SMALL
        val useSegmentedFinal = !useWholeAudioFinal
        val useRealtime = true
        val ready = cachedOnline != null &&
            cachedOnlineResourceId == realtimeResource(session.realtimeModel)
        publish(session, false, if (ready) "正在启动本地录音…" else "正在准备本地模型…", "", "preparing")
        Thread({
            var online: OnlineRecognizer? = null
            var stream: OnlineStream? = null
            var record: AudioRecord? = null
            try {
                var committedText = ""
                online = getOnlineRecognizer(session.realtimeModel)
                stream = online.createStream()
                if (session.cancelled.get() || !session.running.get() || !isCurrent(session)) {
                    finish(session, "本次识别已取消", "", false)
                    return@Thread
                }
                val minimum = AudioRecord.getMinBufferSize(
                    16000,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
                )
                record = AudioRecord(
                    MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    16000,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    maxOf(minimum * 2, 6400)
                )
                audioRecord = record
                val correctionSegments = ArrayList<FloatArray>()
                val pendingCorrectionChunks = ArrayList<FloatArray>()
                val wholeAudioChunks = ArrayList<FloatArray>()
                var pendingCorrectionSamples = 0
                var wholeAudioSamples = 0
                var recordedSamples = 0
                var nextHeartbeat = 16000 * 15
                val maxSamples = 16000 * 60 * 10
                val shorts = ShortArray(1600)
                record.startRecording()
                if (record.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
                    throw IllegalStateException("麦克风没有进入录音状态")
                }
                session.captureStartedAt = System.currentTimeMillis()
                logger.info("麦克风开始收音", operationId(session))
                publish(
                    session,
                    true,
                    if (useRealtime) "本地识别正在聆听…" else "正在录音，停止后整段识别…",
                    "",
                    "listening"
                )
                while (session.running.get() && recordedSamples < maxSamples && isCurrent(session)) {
                    val count = record.read(shorts, 0, shorts.size)
                    if (count < 0) throw IllegalStateException("读取麦克风失败，错误编号=$count")
                    if (count == 0) continue
                    val samples = FloatArray(count) { shorts[it] / 32768.0f }
                    recordedSamples += count
                    session.recordedSamples = recordedSamples
                    if (useSegmentedFinal) {
                        pendingCorrectionChunks += samples
                        pendingCorrectionSamples += count
                    }
                    if (useWholeAudioFinal || session.testModeEnabled) {
                        wholeAudioChunks += samples
                        wholeAudioSamples += count
                    }
                    publishLevel(session, AudioLevelMeter.fromPcm16(shorts, count))
                    if (useRealtime) {
                        stream!!.acceptWaveform(samples, 16000)
                        while (online!!.isReady(stream)) online.decode(stream)
                        val partial = RecognitionText.formatRealtime(online.getResult(stream).text)
                        val combined = RecognitionText.combineSegments(committedText, partial)
                        if (combined != session.text) {
                            session.text = combined
                            markResultUpdate(session)
                            publish(session, true, "正在本地实时识别…", combined, "listening")
                        }
                        if (online!!.isEndpoint(stream)) {
                            committedText = RecognitionText.combineSegments(committedText, partial)
                            if (useSegmentedFinal && pendingCorrectionSamples > 0) {
                                correctionSegments += flattenSamples(
                                    pendingCorrectionChunks,
                                    pendingCorrectionSamples
                                )
                                pendingCorrectionChunks.clear()
                                pendingCorrectionSamples = 0
                            }
                            online.reset(stream)
                            session.endpointCount++
                            session.text = committedText
                            publish(session, true, "已识别一段，请继续说话…", committedText, "listening")
                        }
                    }
                    if (recordedSamples >= nextHeartbeat) {
                        logger.info(
                            "识别会话运行中，收音秒数=${recordedSamples / 16000}，结果更新=${session.resultUpdates}，分段=${session.endpointCount}",
                            operationId(session)
                        )
                        nextHeartbeat += 16000 * 15
                    }
                }
                if (recordedSamples >= maxSamples) {
                    session.running.set(false)
                    publish(session, false, "已达到 10 分钟上限，正在生成文字…", session.text, "processing")
                }
                record.stop()
                record.release()
                record = null
                audioRecord = null
                if (session.cancelled.get() || !isCurrent(session)) {
                    finish(session, "本次识别已取消", "", false)
                    return@Thread
                }
                var realtime = session.text
                if (useRealtime) {
                    stream!!.inputFinished()
                    while (online!!.isReady(stream)) online.decode(stream)
                    val tail = RecognitionText.formatRealtime(online.getResult(stream).text)
                    realtime = RecognitionText.combineSegments(committedText, tail).ifBlank { session.text }
                    stream.release()
                    stream = null
                }
                if (useSegmentedFinal && pendingCorrectionSamples > 0) {
                    correctionSegments += flattenSamples(
                        pendingCorrectionChunks,
                        pendingCorrectionSamples
                    )
                }
                val wholeAudio = if (useWholeAudioFinal || session.testModeEnabled) {
                    flattenSamples(wholeAudioChunks, wholeAudioSamples)
                } else {
                    FloatArray(0)
                }
                wholeAudioChunks.clear()
                pendingCorrectionChunks.clear()
                enqueueFinal(
                    FinalJob(
                        session = session,
                        realtime = realtime,
                        correctionSegments = correctionSegments.toList(),
                        wholeAudio = wholeAudio,
                        correctionResourceId = correctionId,
                        useTranscribe = useTranscribe,
                    )
                )
                correctionSegments.clear()
            } catch (e: Throwable) {
                if (e is ThreadDeath) throw e
                if (session.cancelled.get()) {
                    finish(session, "本次识别已取消", "", false)
                } else {
                    logger.error("本地识别失败，方式=$engine", e, operationId(session))
                    finish(session, "本地识别失败，请检查麦克风或校验模型资源。", session.text, false)
                }
            } finally {
                session.running.set(false)
                runCatching { record?.stop() }
                runCatching { record?.release() }
                if (audioRecord === record) audioRecord = null
                runCatching { stream?.release() }
                localWorkerActive.set(false)
                main.post {
                    if (!isBusy()) {
                        drainPendingModelReloadsIfIdle()
                        if (preloadPending.get()) preloadModels()
                    }
                }
            }
        }, "本地语音识别-${session.id}").start()
    }

    private fun enqueueFinal(job: FinalJob) {
        val accepted = synchronized(finalQueueLock) {
            if (finalQueue.size >= MAX_FINAL_QUEUE_SIZE) false
            else {
                finalQueue.addLast(job)
                true
            }
        }
        if (!accepted) {
            logger.warning(
                "最终识别队列已满，改为保存实时结果，队列上限=$MAX_FINAL_QUEUE_SIZE",
                operationId(job.session),
            )
            finish(
                job.session,
                "最终识别队列已满，已保存实时文字",
                job.realtime,
                job.realtime.isNotBlank(),
            )
            return
        }

        main.post {
            synchronized(stateLock) {
                if (activeSession === job.session) activeSession = null
                listening = false
                currentPhase = "idle"
                currentStatus = if (processingFinalJob == null) {
                    "正在生成最终文字，可继续识别"
                } else {
                    "已加入最后识别队列，可继续识别"
                }
                lastText = job.realtime
            }
            listeners.forEach { it.onAudioLevel(0f) }
            notifyQueueChanged()
        }
        logger.info(
            "录音已加入最终识别队列，等待数量=${synchronized(finalQueueLock) { finalQueue.size }}",
            operationId(job.session),
        )
        startFinalWorker()
    }

    private fun startFinalWorker() {
        if (!finalWorkerActive.compareAndSet(false, true)) return
        Thread({
            try {
                while (true) {
                    val job = synchronized(finalQueueLock) {
                        if (finalQueue.isEmpty()) null else finalQueue.removeFirst()
                    } ?: break
                    processingFinalJob = job
                    notifyQueueChanged()
                    processFinal(job)
                    processingFinalJob = null
                    notifyQueueChanged()
                }
            } finally {
                processingFinalJob = null
                finalWorkerActive.set(false)
                val needsRestart = synchronized(finalQueueLock) { finalQueue.isNotEmpty() }
                if (needsRestart) {
                    startFinalWorker()
                } else {
                    main.post {
                        drainPendingModelReloadsIfIdle()
                        if (preloadPending.get() || activeSession == null) preloadModels()
                    }
                }
            }
        }, "最终识别队列").start()
    }

    private fun processFinal(job: FinalJob) {
        val session = job.session
        var secondPassFailed = false
        try {
            val secondPass = try {
                when (session.finalModel) {
                    FINAL_FASTER_WHISPER_SMALL -> {
                        notifyFinalProgress("正在使用 Faster-Whisper Small 生成最终文字…")
                        RecognitionText.cleanRealtime(runTranscribeFinal(session, job.wholeAudio))
                    }
                    FINAL_QWEN3_ASR_06B_INT8, FINAL_QWEN3_ASR_17B_Q5_K_M -> {
                        notifyFinalProgress("正在使用最终模型分段整理文字…")
                        var correctedText = ""
                        job.correctionSegments.forEachIndexed { index, segment ->
                            val segmentText = if (session.finalModel == FINAL_QWEN3_ASR_06B_INT8) {
                                runOfflineCorrection(segment, job.correctionResourceId!!)
                            } else {
                                runTranscribeFinal(session, segment)
                            }
                            correctedText = RecognitionText.combineSegments(correctedText, segmentText)
                            logger.info(
                                "分段最终识别完成，片段=${index + 1}/${job.correctionSegments.size}，样本=${segment.size}，字符数=${segmentText.length}",
                                operationId(session),
                            )
                        }
                        correctedText
                    }
                    else -> ""
                }
            } catch (error: Throwable) {
                if (error is ThreadDeath) throw error
                secondPassFailed = true
                logger.error(
                    "二次识别失败，改用实时识别结果，方式=${session.engine}",
                    error,
                    operationId(session),
                )
                ""
            }
            val final = if (job.useTranscribe) {
                RecognitionText.chooseWhisperFinal(
                    realtime = job.realtime,
                    whisper = secondPass,
                    audioSampleCount = session.recordedSamples,
                )
            } else {
                RecognitionText.chooseFinal(job.realtime, secondPass)
            }
            val finalText = final.text
            logger.info(
                "最终结果候选选择完成，来源=${final.source}，实时字符数=${job.realtime.length}，二次识别字符数=${secondPass.length}",
                operationId(session),
            )
            val testCapture = if (session.testModeEnabled) {
                TestCapture(
                    realtimeDraft = job.realtime,
                    secondPassText = secondPass.takeIf { it.isNotBlank() },
                    selectedResult = if (final.source == RecognitionResultSource.CORRECTED) {
                        TestSelectedResult.SECOND_PASS
                    } else {
                        TestSelectedResult.REALTIME_DRAFT
                    },
                    audioSamples = job.wholeAudio,
                )
            } else {
                null
            }
            completeFinal(
                session = session,
                status = when {
                    finalText.isBlank() -> "没有识别到文字，请再试一次。"
                    secondPassFailed -> "二次识别失败，已保留实时结果"
                    job.useTranscribe && final.source == RecognitionResultSource.REALTIME ->
                        "最终模型未产生有效结果，已保留实时结果"
                    final.source == RecognitionResultSource.REALTIME -> "已保留更完整的实时结果"
                    else -> "最终识别完成"
                },
                text = finalText,
                save = finalText.isNotBlank(),
                testCapture = testCapture,
            )
        } catch (error: Throwable) {
            if (error is ThreadDeath) throw error
            logger.error("后台最终识别失败，方式=${session.engine}", error, operationId(session))
            completeFinal(
                session = session,
                status = "最终识别失败，已保留实时文字",
                text = job.realtime,
                save = job.realtime.isNotBlank(),
            )
        }
    }

    private fun completeFinal(
        session: Session,
        status: String,
        text: String,
        save: Boolean,
        testCapture: TestCapture? = null,
    ) {
        if (!session.finished.compareAndSet(false, true)) return
        saveHistory(session, text, save, testCapture)?.let { throw it }
        lastFinalText = text
        main.post {
            if (activeSession == null) {
                lastText = text
                currentPhase = "idle"
                currentStatus = status
            }
            val totalDuration = System.currentTimeMillis() - session.createdAt
            logger.info(
                "排队识别会话结束，方式=${session.engine}，总耗时=${totalDuration}毫秒，样本=${session.recordedSamples}，字符数=${text.length}，已保存=$save",
                operationId(session),
            )
            notifyQueueChanged()
        }
    }

    private fun notifyFinalProgress(status: String) = main.post {
        if (activeSession == null) currentStatus = status
        notifyQueueChanged()
    }

    private fun notifyQueueChanged() = main.post {
        listeners.forEach { it.onRecognitionState(listening, currentStatus, lastText) }
    }

    private fun runOfflineCorrection(samples: FloatArray, resourceId: String): String {
        if (samples.isEmpty()) return ""
        val offline = getOfflineRecognizer(resourceId)
        val stream = offline.createStream()
        return try {
            stream.acceptWaveform(samples, 16000)
            offline.decode(stream)
            RecognitionText.cleanRealtime(offline.getResult(stream).text)
        } finally {
            stream.release()
        }
    }

    private fun runTranscribeFinal(session: Session, samples: FloatArray): String {
        val waiting = AtomicBoolean(true)
        val started = System.currentTimeMillis()
        val heartbeat = Thread({
            while (waiting.get()) {
                try {
                    Thread.sleep(15_000)
                } catch (_: InterruptedException) {
                    return@Thread
                }
                if (waiting.get()) {
                    logger.info(
                        "最终模型仍在处理中，已等待=${System.currentTimeMillis() - started}毫秒",
                        operationId(session),
                    )
                }
            }
        }, "最终识别心跳-${session.id}").apply {
            isDaemon = true
            start()
        }
        return try {
            getTranscribeRecognizer(session.finalModel).transcribe(samples, "auto")
        } finally {
            waiting.set(false)
            heartbeat.interrupt()
            logger.info(
                "最终识别阶段结束，耗时=${System.currentTimeMillis() - started}毫秒",
                operationId(session),
            )
        }
    }

    private fun flattenSamples(chunks: List<FloatArray>, totalSamples: Int): FloatArray {
        if (totalSamples <= 0) return FloatArray(0)
        return FloatArray(totalSamples).also { target ->
            var offset = 0
            chunks.forEach { part ->
                part.copyInto(target, offset)
                offset += part.size
            }
        }
    }

    private fun first(bundle: Bundle?) = bundle
        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        ?.firstOrNull()
        ?.trim()
        .orEmpty()

    private fun publish(
        session: Session,
        capturing: Boolean,
        status: String,
        text: String,
        phase: String = if (capturing) "listening" else "preparing"
    ) = main.post {
        if (!isCurrent(session)) return@post
        listening = capturing
        currentPhase = phase
        currentStatus = status
        lastText = text
        listeners.forEach { it.onRecognitionState(capturing, status, lastText) }
    }

    private fun publishIdle(status: String) = main.post {
        if (activeSession == null) {
            listening = false
            currentPhase = "idle"
            currentStatus = status
            listeners.forEach { it.onRecognitionState(false, status, lastText) }
        }
    }

    private fun publishLevel(session: Session, level: Float) = main.post {
        if (isCurrent(session)) listeners.forEach { it.onAudioLevel(level.coerceIn(0f, 1f)) }
    }

    private fun markResultUpdate(session: Session) {
        session.resultUpdates++
        if (session.firstResultAt == 0L) {
            session.firstResultAt = System.currentTimeMillis()
            val base = session.captureStartedAt.takeIf { it > 0 } ?: session.createdAt
            logger.info("收到首个非空识别结果，延迟=${session.firstResultAt - base}毫秒", operationId(session))
        }
    }

    private fun operationId(session: Session) = "recognition-${session.id}"

    private fun finish(
        session: Session,
        status: String,
        text: String,
        save: Boolean,
        testCapture: TestCapture? = null,
    ) {
        if (activeSession !== session || !session.finished.compareAndSet(false, true)) return
        session.running.set(false)
        session.retry?.let(main::removeCallbacks)
        session.retry = null
        session.systemAttempt++
        runCatching { session.recognizer?.cancel() }
        runCatching { session.recognizer?.destroy() }
        session.recognizer = null
        val fatalThreadDeath = saveHistory(session, text, save, testCapture)
        main.post {
            synchronized(stateLock) {
                if (activeSession !== session) return@post
                activeSession = null
                listening = false
                lastText = text
                currentPhase = "idle"
                currentStatus = status
            }
            listeners.forEach { it.onAudioLevel(0f) }
            listeners.forEach { it.onRecognitionState(false, status, lastText) }
            val totalDuration = System.currentTimeMillis() - session.createdAt
            val captureDuration = if (session.captureStartedAt > 0) {
                System.currentTimeMillis() - session.captureStartedAt
            } else 0
            logger.info(
                "识别会话结束，方式=${session.engine}，总耗时=${totalDuration}毫秒，收音耗时=${captureDuration}毫秒，样本=${session.recordedSamples}，结果更新=${session.resultUpdates}，分段=${session.endpointCount}，字符数=${text.length}，已保存=$save",
                operationId(session)
            )
            drainPendingModelReloadsIfIdle()
            if (preloadPending.get() || selectedEngine() != session.engine) preloadModels()
        }
        fatalThreadDeath?.let { throw it }
    }

    private fun saveHistory(
        session: Session,
        text: String,
        save: Boolean,
        testCapture: TestCapture?,
    ): ThreadDeath? {
        var fatalThreadDeath: ThreadDeath? = null
        if (save && text.isNotBlank()) {
            try {
                if (testCapture != null) {
                    history.addWithTestData(
                        finalText = text,
                        engine = session.engine,
                        realtimeDraft = testCapture.realtimeDraft,
                        secondPassText = testCapture.secondPassText,
                        selectedResult = testCapture.selectedResult,
                        audioSamples = testCapture.audioSamples,
                    )
                } else {
                    history.add(text, session.engine)
                }
            } catch (e: Throwable) {
                if (e is ThreadDeath) {
                    fatalThreadDeath = e
                } else {
                    runCatching { logger.error("保存识别历史失败", e, operationId(session)) }
                }
            }
        }
        return fatalThreadDeath
    }

    private const val MAX_FINAL_QUEUE_SIZE = 8
}
