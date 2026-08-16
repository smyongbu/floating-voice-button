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
import com.k2fsa.sherpa.onnx.OfflineParaformerModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineRecognizer
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineStream
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

object RecognitionController {
    const val ENGINE_DUAL = "local_dual"
    const val ENGINE_ZIPFORMER = "local_zipformer"
    const val ENGINE_PARAFORMER = "local_paraformer"
    const val ENGINE_SYSTEM = "system"
    val validEngines = setOf(ENGINE_DUAL, ENGINE_ZIPFORMER, ENGINE_PARAFORMER, ENGINE_SYSTEM)

    interface Listener {
        fun onRecognitionState(listening: Boolean, status: String, text: String)
        fun onAudioLevel(level: Float) = Unit
    }

    private class Session(val id: Long, val engine: String) {
        val cancelled = AtomicBoolean(false)
        val finished = AtomicBoolean(false)
        val running = AtomicBoolean(true)
        val stopRequested = AtomicBoolean(false)
        @Volatile var text = ""
        @Volatile var recognizer: SpeechRecognizer? = null
        @Volatile var retry: Runnable? = null
        @Volatile var systemAttempt = 0
        @Volatile var systemRetry = 0
    }

    private val listeners = CopyOnWriteArrayList<Listener>()
    private val main = Handler(Looper.getMainLooper())
    private val stateLock = Any()
    private val sessionIds = AtomicLong(0)
    private val preloadStarted = AtomicBoolean(false)
    private val localWorkerActive = AtomicBoolean(false)
    private val modelLock = Any()
    private lateinit var app: Context
    private lateinit var logger: AppLogger
    private lateinit var history: HistoryStore
    @Volatile private var activeSession: Session? = null
    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var cachedOnline: OnlineRecognizer? = null
    @Volatile private var cachedOffline: OfflineRecognizer? = null
    @Volatile private var modelStatus = "正在准备本地模型…"
    @Volatile private var listening = false
    @Volatile private var lastText = ""

    fun init(context: Context) {
        if (!::app.isInitialized) {
            app = context.applicationContext
            logger = AppLogger(app)
            history = HistoryStore(app)
            val saved = app.getSharedPreferences("settings", 0).getString("engine", ENGINE_DUAL)
            if (saved == "local") setEngine(ENGINE_DUAL)
            preloadModels()
        }
    }

    fun addListener(listener: Listener) {
        listeners += listener
        listener.onRecognitionState(listening, if (listening) "正在识别…" else modelStatus, lastText)
    }

    fun removeListener(listener: Listener) { listeners -= listener }

    fun selectedEngine(): String = app.getSharedPreferences("settings", 0)
        .getString("engine", ENGINE_DUAL)
        .let { if (it in validEngines) it!! else ENGINE_DUAL }

    fun setEngine(engine: String) {
        app.getSharedPreferences("settings", 0).edit()
            .putString("engine", if (engine in validEngines) engine else ENGINE_DUAL)
            .apply()
    }

    fun isListening() = activeSession?.finished?.get() == false

    fun toggle() { if (isListening()) stop() else start() }

    fun start() {
        if (app.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            publishIdle("没有麦克风权限，请在主界面授权。")
            return
        }
        val session = synchronized(stateLock) {
            if (activeSession != null || localWorkerActive.get()) null
            else Session(sessionIds.incrementAndGet(), selectedEngine()).also {
                activeSession = it
                listening = true
                lastText = ""
            }
        } ?: return
        publishLevel(session, 0f)
        if (session.engine == ENGINE_SYSTEM) startSystem(session) else startLocal(session)
    }

    fun stop() {
        val session = activeSession ?: return
        if (session.finished.get()) return
        if (session.engine == ENGINE_SYSTEM) {
            session.stopRequested.set(true)
            val speech = session.recognizer
            if (session.retry != null || speech == null) {
                session.retry?.let(main::removeCallbacks)
                session.retry = null
                finish(
                    session,
                    if (session.text.isBlank()) "系统识别已停止，没有可保存的文字。" else "系统识别完成",
                    session.text,
                    session.text.isNotBlank()
                )
            } else {
                publish(session, true, "正在整理文字…", session.text)
                speech.stopListening()
            }
        } else {
            session.running.set(false)
            publish(
                session,
                true,
                if (session.engine == ENGINE_ZIPFORMER) "正在完成实时识别…" else "正在对整段文字进行校正…",
                session.text
            )
        }
    }

    fun cancel() {
        val session = activeSession ?: return
        if (session.finished.get()) return
        session.cancelled.set(true)
        session.running.set(false)
        logger.info("请求取消识别，方式=${session.engine}")
        if (session.engine == ENGINE_SYSTEM) {
            session.retry?.let(main::removeCallbacks)
            session.retry = null
            session.systemAttempt++
            runCatching { session.recognizer?.cancel() }
            runCatching { session.recognizer?.destroy() }
            session.recognizer = null
            finish(session, "本次识别已取消", "", false)
        } else {
            publish(session, true, "正在取消本次识别…", session.text)
        }
    }

    private fun preloadModels() {
        if (!preloadStarted.compareAndSet(false, true)) return
        Thread({
            val started = System.currentTimeMillis()
            modelStatus = "正在预加载 Zipformer 和 Paraformer…"
            notifyModelStatus()
            try {
                getOnlineRecognizer()
                getOfflineRecognizer()
                modelStatus = "本地模型已加载，准备就绪"
                logger.info("本地模型预加载完成，耗时=${System.currentTimeMillis() - started}毫秒")
            } catch (e: Exception) {
                modelStatus = "本地模型加载失败，请重新安装应用"
                logger.error("本地模型预加载失败", e)
            }
            notifyModelStatus()
        }, "本地模型预加载").start()
    }

    private fun notifyModelStatus() = main.post {
        if (activeSession == null) listeners.forEach { it.onRecognitionState(false, modelStatus, lastText) }
    }

    private fun getOnlineRecognizer(): OnlineRecognizer {
        cachedOnline?.let { return it }
        synchronized(modelLock) {
            cachedOnline?.let { return it }
            val dir = "models/zipformer-bilingual"
            return OnlineRecognizer(
                app.assets,
                OnlineRecognizerConfig(
                    modelConfig = OnlineModelConfig(
                        transducer = OnlineTransducerModelConfig(
                            encoder = "$dir/encoder-epoch-99-avg-1.int8.onnx",
                            decoder = "$dir/decoder-epoch-99-avg-1.onnx",
                            joiner = "$dir/joiner-epoch-99-avg-1.int8.onnx"
                        ),
                        tokens = "$dir/tokens.txt",
                        numThreads = 2,
                        provider = "cpu"
                    ),
                    enableEndpoint = false
                )
            ).also { cachedOnline = it }
        }
    }

    private fun getOfflineRecognizer(): OfflineRecognizer {
        cachedOffline?.let { return it }
        synchronized(modelLock) {
            cachedOffline?.let { return it }
            val dir = "models/paraformer"
            return OfflineRecognizer(
                app.assets,
                OfflineRecognizerConfig(
                    modelConfig = OfflineModelConfig(
                        paraformer = OfflineParaformerModelConfig("$dir/model.int8.onnx"),
                        tokens = "$dir/tokens.txt",
                        numThreads = 4,
                        provider = "cpu",
                        modelType = "paraformer"
                    )
                )
            ).also { cachedOffline = it }
        }
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
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, app.packageName)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1800L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1200L)
            }
            publish(session, true, "正在连接系统识别服务…", "")
            speech.startListening(intent)
            logger.info("启动系统默认识别")
        } catch (e: Exception) {
            logger.error("系统识别启动失败", e)
            finish(session, "系统识别启动失败，请改用本地识别。", session.text, false)
        }
    }

    private fun systemListener(session: Session, attempt: Int) = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publish(session, true, "请开始说话", session.text)
        }

        override fun onBeginningOfSpeech() {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publish(session, true, "正在系统识别…", session.text)
        }

        override fun onRmsChanged(rmsdB: Float) {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publishLevel(session, ((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
        }

        override fun onBufferReceived(buffer: ByteArray?) = Unit

        override fun onEndOfSpeech() {
            if (isCurrent(session, attempt) && !session.cancelled.get())
                publish(session, true, "正在整理文字…", session.text)
        }

        override fun onPartialResults(results: Bundle?) {
            if (!isCurrent(session, attempt) || session.cancelled.get()) return
            first(results).takeIf { it.isNotBlank() }?.let {
                session.text = it
                publish(session, true, "正在系统实时识别…", it)
            }
        }

        override fun onResults(results: Bundle?) {
            if (!isCurrent(session, attempt) || session.cancelled.get()) return
            val text = first(results).ifBlank { session.text }
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
        val ready = (engine == ENGINE_PARAFORMER || cachedOnline != null) &&
            (engine == ENGINE_ZIPFORMER || cachedOffline != null)
        publish(session, true, if (ready) "正在启动本地录音…" else "首次准备本地模型…", "")
        Thread({
            var online: OnlineRecognizer? = null
            var stream: OnlineStream? = null
            var record: AudioRecord? = null
            try {
                val useRealtime = engine != ENGINE_PARAFORMER
                val useCorrection = engine != ENGINE_ZIPFORMER
                if (useRealtime) {
                    online = getOnlineRecognizer()
                    stream = online.createStream()
                }
                if (useCorrection) getOfflineRecognizer()
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
                val chunks = ArrayList<FloatArray>()
                var totalSamples = 0
                var recordedSamples = 0
                val maxSamples = 16000 * 60 * 10
                val shorts = ShortArray(1600)
                record.startRecording()
                publish(
                    session,
                    true,
                    if (useRealtime) "本地识别正在聆听…" else "正在录音，停止后整段识别…",
                    ""
                )
                while (session.running.get() && recordedSamples < maxSamples && isCurrent(session)) {
                    val count = record.read(shorts, 0, shorts.size)
                    if (count < 0) throw IllegalStateException("读取麦克风失败，错误编号=$count")
                    if (count == 0) continue
                    val samples = FloatArray(count) { shorts[it] / 32768.0f }
                    recordedSamples += count
                    if (useCorrection) {
                        chunks += samples
                        totalSamples += count
                    }
                    publishLevel(session, AudioLevelMeter.fromPcm16(shorts, count))
                    if (useRealtime) {
                        stream!!.acceptWaveform(samples, 16000)
                        while (online!!.isReady(stream)) online.decode(stream)
                        val partial = RecognitionText.cleanRealtime(online.getResult(stream).text)
                        if (partial.isNotEmpty() && partial != session.text) {
                            session.text = partial
                            publish(session, true, "正在本地实时识别…", partial)
                        }
                    }
                }
                if (recordedSamples >= maxSamples) {
                    session.running.set(false)
                    publish(session, true, "已达到 10 分钟上限，正在生成文字…", session.text)
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
                    realtime = RecognitionText.cleanRealtime(online.getResult(stream).text).ifBlank { session.text }
                    stream.release()
                    stream = null
                }
                val all = if (useCorrection) {
                    FloatArray(totalSamples).also { target ->
                        var offset = 0
                        chunks.forEach { part ->
                            part.copyInto(target, offset)
                            offset += part.size
                        }
                    }
                } else FloatArray(0)
                val finalText = if (useCorrection) runParaformer(all).ifBlank { realtime } else realtime
                if (session.cancelled.get() || !isCurrent(session)) {
                    finish(session, "本次识别已取消", "", false)
                } else {
                    finish(
                        session,
                        if (finalText.isBlank()) "没有识别到文字，请再试一次。"
                        else if (useCorrection) "整段校正完成" else "实时识别完成",
                        finalText,
                        finalText.isNotBlank()
                    )
                }
            } catch (e: Exception) {
                if (session.cancelled.get()) {
                    finish(session, "本次识别已取消", "", false)
                } else {
                    logger.error("本地识别失败，方式=$engine", e)
                    finish(session, "本地识别失败，请检查麦克风权限或重新安装应用。", session.text, false)
                }
            } finally {
                session.running.set(false)
                runCatching { record?.stop() }
                runCatching { record?.release() }
                if (audioRecord === record) audioRecord = null
                runCatching { stream?.release() }
                localWorkerActive.set(false)
            }
        }, "本地语音识别-${session.id}").start()
    }

    private fun runParaformer(samples: FloatArray): String {
        if (samples.isEmpty()) return ""
        val offline = getOfflineRecognizer()
        val stream = offline.createStream()
        return try {
            stream.acceptWaveform(samples, 16000)
            offline.decode(stream)
            offline.getResult(stream).text.trim()
        } finally {
            stream.release()
        }
    }

    private fun first(bundle: Bundle?) = bundle
        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        ?.firstOrNull()
        ?.trim()
        .orEmpty()

    private fun publish(session: Session, active: Boolean, status: String, text: String) = main.post {
        if (!isCurrent(session)) return@post
        listening = active
        if (text.isNotBlank()) session.text = text
        lastText = session.text
        listeners.forEach { it.onRecognitionState(active, status, lastText) }
    }

    private fun publishIdle(status: String) = main.post {
        if (activeSession == null) listeners.forEach { it.onRecognitionState(false, status, lastText) }
    }

    private fun publishLevel(session: Session, level: Float) = main.post {
        if (isCurrent(session)) listeners.forEach { it.onAudioLevel(level.coerceIn(0f, 1f)) }
    }

    private fun finish(session: Session, status: String, text: String, save: Boolean) {
        if (activeSession !== session || !session.finished.compareAndSet(false, true)) return
        session.running.set(false)
        session.retry?.let(main::removeCallbacks)
        session.retry = null
        session.systemAttempt++
        runCatching { session.recognizer?.cancel() }
        runCatching { session.recognizer?.destroy() }
        session.recognizer = null
        if (save && text.isNotBlank()) {
            try {
                history.add(text, session.engine)
            } catch (e: Exception) {
                logger.error("保存识别历史失败", e)
            }
        }
        main.post {
            synchronized(stateLock) {
                if (activeSession !== session) return@post
                activeSession = null
                listening = false
                lastText = text
            }
            listeners.forEach { it.onAudioLevel(0f) }
            listeners.forEach { it.onRecognitionState(false, status, lastText) }
            logger.info("识别结束，方式=${session.engine}，字符数=${text.length}，已保存=$save")
        }
    }
}
