package com.smyongbu.voiceinput

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.content.ContextCompat
import androidx.webkit.WebViewAssetLoader
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.util.concurrent.Executors
import kotlin.math.roundToInt

class MainActivity : Activity(), RecognitionController.Listener, ModelResourceManager.Listener {
    private enum class PendingAudioAction { RECOGNITION, OVERLAY }

    private lateinit var webView: WebView
    private lateinit var historyStore: HistoryStore
    private lateinit var logger: AppLogger
    private val databaseExecutor = Executors.newSingleThreadExecutor()
    private var pageReady = false
    private var currentPage = "recording"
    private var waitingForOverlayPermission = false
    private var waitingForNotificationPermission = false
    private var pendingAudioAction: PendingAudioAction? = null
    private var lastAudioDispatchAt = 0L
    private var availableResourceIds = emptySet<String>()
    private val overlayStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == FloatingVoiceService.ACTION_STATE_CHANGED) emitSettings()
        }
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        currentPage = state?.getString(STATE_PAGE).takeIf { it in VALID_PAGES } ?: "recording"
        setContentView(R.layout.activity_main)
        logger = AppLogger(this)
        historyStore = HistoryStore(applicationContext)
        ModelResourceManager.init(this)
        RecognitionController.init(this)
        availableResourceIds = ModelResourceManager.states()
            .filter { it.status == "available" }
            .mapTo(mutableSetOf()) { it.id }
        webView = findViewById(R.id.webView)
        configureWebView()
        logger.info("HTML 界面宿主已启动，版本=${appVersion()}", "ui-start")
    }

    @SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
    private fun configureWebView() {
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setAllowFileAccessFromFileURLs(false)
            setAllowUniversalAccessFromFileURLs(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            builtInZoomControls = false
            displayZoomControls = false
            mediaPlaybackRequiresUserGesture = true
            cacheMode = WebSettings.LOAD_NO_CACHE
            textZoom = (resources.configuration.fontScale * 100).roundToInt().coerceAtLeast(1)
        }
        CookieManager.getInstance().setAcceptCookie(false)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false)
        WebView.setWebContentsDebuggingEnabled(
            applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        )
        webView.isVerticalScrollBarEnabled = false
        webView.addJavascriptInterface(WebBridge(), "NativeApp")
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val url = request.url
                return if (url.scheme == "https" &&
                    url.host == APP_ASSET_HOST &&
                    url.path.orEmpty().startsWith("/assets/")
                ) {
                    assetLoader.shouldInterceptRequest(url)
                } else {
                    WebResourceResponse(
                        "text/plain",
                        "UTF-8",
                        403,
                        "Blocked",
                        emptyMap(),
                        ByteArrayInputStream(ByteArray(0))
                    )
                }
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                return url.scheme != "https" || url.host != APP_ASSET_HOST ||
                    url.path != "/assets/web/index.html"
            }

            override fun onPageFinished(view: WebView, url: String) {
                logger.info("HTML 界面加载完成", "ui-load")
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(message: ConsoleMessage): Boolean {
                if (message.messageLevel() == ConsoleMessage.MessageLevel.ERROR) {
                    logger.error(
                        "网页脚本发生错误，行=${message.lineNumber()}，来源=${message.sourceId().substringAfterLast('/').take(80)}",
                        operationId = "ui-script"
                    )
                }
                return true
            }
        }
        webView.loadUrl(ENTRY_URL)
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(FloatingVoiceService.ACTION_STATE_CHANGED)
        ContextCompat.registerReceiver(
            this,
            overlayStateReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
    }

    override fun onStop() {
        runCatching { unregisterReceiver(overlayStateReceiver) }
        super.onStop()
    }

    override fun onResume() {
        super.onResume()
        RecognitionController.addListener(this)
        ModelResourceManager.addListener(this)
        if (waitingForOverlayPermission && Settings.canDrawOverlays(this)) {
            waitingForOverlayPermission = false
            enableOverlayAfterPermissions()
        }
        if (pageReady) {
            emitFullState()
            emitHistory()
        }
    }

    override fun onPause() {
        RecognitionController.removeListener(this)
        ModelResourceManager.removeListener(this)
        super.onPause()
    }

    override fun onDestroy() {
        RecognitionController.removeListener(this)
        ModelResourceManager.removeListener(this)
        pageReady = false
        databaseExecutor.execute { historyStore.close() }
        databaseExecutor.shutdown()
        webView.removeJavascriptInterface("NativeApp")
        webView.stopLoading()
        webView.destroy()
        logger.info("HTML 界面宿主已关闭", "ui-stop")
        super.onDestroy()
    }

    override fun onRecognitionState(listening: Boolean, status: String, text: String) {
        runOnUiThread {
            emit(JSONObject().apply {
                put("type", "recognition")
                put("recognition", recognitionJson())
            })
            if (!RecognitionController.isListening()) emitHistory()
        }
    }

    override fun onAudioLevel(level: Float) {
        val now = System.currentTimeMillis()
        if (now - lastAudioDispatchAt < 50) return
        lastAudioDispatchAt = now
        runOnUiThread {
            emit(JSONObject().apply {
                put("type", "audioLevel")
                put("level", level.coerceIn(0f, 1f).toDouble())
            })
        }
    }

    override fun onModelResourcesChanged(states: List<ModelResourceState>) {
        runOnUiThread {
            val nowAvailable = states.filter { it.status == "available" }.mapTo(mutableSetOf()) { it.id }
            (nowAvailable - availableResourceIds).forEach(RecognitionController::refreshModel)
            availableResourceIds = nowAvailable
            emit(JSONObject().apply {
                put("type", "resources")
                put("resources", resourcesJson(states))
            })
        }
    }

    private inner class WebBridge {
        @JavascriptInterface
        fun ready() = runOnUiThread {
            pageReady = true
            emitFullState()
            emitHistory()
            logger.info("HTML 界面桥接已就绪", "ui-bridge")
        }

        @JavascriptInterface
        fun getInitialState(): String = initialStateJson().toString()

        @JavascriptInterface
        fun setCurrentPage(page: String) {
            if (page in VALID_PAGES) runOnUiThread { currentPage = page }
        }

        @JavascriptInterface
        fun toggleRecognition() = runOnUiThread {
            ensureAudio(PendingAudioAction.RECOGNITION) { RecognitionController.toggle() }
        }

        @JavascriptInterface
        fun cancelRecognition() = runOnUiThread { RecognitionController.cancel() }

        @JavascriptInterface
        fun copyText(raw: String) = runOnUiThread { copyToClipboard(raw.take(MAX_TEXT_LENGTH)) }

        @JavascriptInterface
        fun setEngine(engine: String) = runOnUiThread {
            if (engine !in RecognitionController.validEngines) return@runOnUiThread
            RecognitionController.setEngine(engine)
            logger.info("识别方案已更改，方式=$engine", "settings-engine")
            emitSettings()
            showMessage("识别方案已保存。")
        }

        @JavascriptInterface
        fun setOverlayEnabled(enabled: Boolean) = runOnUiThread { changeOverlay(enabled) }

        @JavascriptInterface
        fun setOverlayTextEnabled(enabled: Boolean) = runOnUiThread {
            OverlayPreferences.setTextEnabled(this@MainActivity, enabled)
            notifyOverlayAppearanceChanged()
            logger.info("悬浮文字框设置已更改，显示=$enabled", "settings-overlay-text")
            emitSettings()
        }

        @JavascriptInterface
        fun setOverlayOpacity(percent: Int) = runOnUiThread {
            val value = percent.coerceIn(35, 100)
            OverlayPreferences.setOpacity(this@MainActivity, value)
            notifyOverlayAppearanceChanged()
            logger.info("悬浮球透明度已更改，百分比=$value", "settings-overlay-opacity")
            emitSettings()
        }

        @JavascriptInterface
        fun setOverlaySize(sizeDp: Int) = runOnUiThread {
            val value = sizeDp.coerceIn(48, 88)
            OverlayPreferences.setSize(this@MainActivity, value)
            notifyOverlayAppearanceChanged()
            logger.info("悬浮球大小已更改，大小=${value}dp", "settings-overlay-size")
            emitSettings()
        }

        @JavascriptInterface
        fun copyHistory(id: Long) {
            databaseExecutor.execute {
                val item = historyStore.get(id)
                runOnUiThread {
                    if (item == null) showMessage("这条记录已经不存在。")
                    else copyToClipboard(item.text)
                }
            }
        }

        @JavascriptInterface
        fun deleteHistory(id: Long) {
            databaseExecutor.execute {
                historyStore.delete(id)
                logger.info("已删除一条识别历史", "history-delete")
                emitHistory()
            }
        }

        @JavascriptInterface
        fun clearHistory() {
            databaseExecutor.execute {
                historyStore.clear()
                logger.info("已清空识别历史", "history-clear")
                emitHistory()
            }
        }

        @JavascriptInterface
        fun downloadResource(id: String) = runOnUiThread { ModelResourceManager.startOrResume(id) }

        @JavascriptInterface
        fun pauseResource(id: String) = runOnUiThread { ModelResourceManager.pause(id) }

        @JavascriptInterface
        fun verifyResource(id: String) = runOnUiThread {
            if (RecognitionController.isListening()) showMessage("识别进行中，暂时不能校验模型。")
            else ModelResourceManager.verify(id)
        }

        @JavascriptInterface
        fun copyDiagnostics() = runOnUiThread {
            copyToClipboard(diagnosticsText(), "安卓语音输入诊断信息", "诊断信息已复制。")
        }

        @JavascriptInterface
        fun deleteResource(id: String) = runOnUiThread {
            if (RecognitionController.isListening()) {
                showMessage("识别进行中，暂时不能删除模型。")
                return@runOnUiThread
            }
            if (!RecognitionController.unloadModel(id)) {
                showMessage("模型正在使用，暂时不能删除。")
                return@runOnUiThread
            }
            databaseExecutor.execute {
                val deleted = ModelResourceManager.delete(id)
                runOnUiThread {
                    showMessage(if (deleted) "模型已从手机中删除。" else "模型删除失败，请稍后重试。")
                }
            }
        }
    }

    private fun ensureAudio(action: PendingAudioAction, block: () -> Unit) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            pendingAudioAction = null
            block()
            return
        }
        pendingAudioAction = action
        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO)
    }

    private fun changeOverlay(enabled: Boolean) {
        if (!enabled) {
            waitingForOverlayPermission = false
            stopService(Intent(this, FloatingVoiceService::class.java))
            logger.info("用户关闭悬浮小球", "overlay")
            webView.postDelayed({ emitSettings() }, 200)
            return
        }
        if (!Settings.canDrawOverlays(this)) {
            waitingForOverlayPermission = true
            emitSettings()
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            return
        }
        ensureAudio(PendingAudioAction.OVERLAY) { enableOverlayAfterPermissions() }
    }

    private fun enableOverlayAfterPermissions() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            !waitingForNotificationPermission
        ) {
            waitingForNotificationPermission = true
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
            return
        }
        startOverlayService()
    }

    private fun startOverlayService() {
        waitingForNotificationPermission = false
        startForegroundService(Intent(this, FloatingVoiceService::class.java))
        logger.info("用户开启悬浮小球", "overlay")
        webView.postDelayed({ emitSettings() }, 250)
    }

    private fun notifyOverlayAppearanceChanged() {
        sendBroadcast(
            Intent(FloatingVoiceService.ACTION_APPEARANCE_CHANGED).setPackage(packageName)
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            REQUEST_AUDIO -> {
                val action = pendingAudioAction
                pendingAudioAction = null
                if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
                    when (action) {
                        PendingAudioAction.RECOGNITION -> RecognitionController.toggle()
                        PendingAudioAction.OVERLAY -> enableOverlayAfterPermissions()
                        null -> Unit
                    }
                } else {
                    logger.warning("用户拒绝麦克风权限", "permission-audio")
                    showMessage("需要麦克风权限才能进行语音识别。")
                }
            }
            REQUEST_NOTIFICATIONS -> {
                if (grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
                    logger.warning("用户拒绝通知权限，悬浮服务通知可能不可见", "permission-notification")
                }
                startOverlayService()
            }
        }
    }

    private fun copyToClipboard(
        raw: String,
        label: String = "语音识别文字",
        successMessage: String = "已复制到剪贴板。"
    ) {
        val text = raw.trim()
        if (text.isBlank()) {
            showMessage("还没有可以复制的文字。")
            return
        }
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText(label, text))
        showMessage(successMessage)
    }

    private fun diagnosticsText(): String = buildString {
        appendLine("安卓语音输入诊断信息")
        appendLine("应用版本：${appVersion()}")
        appendLine("系统：Android ${Build.VERSION.RELEASE}（API ${Build.VERSION.SDK_INT}）")
        appendLine("设备：${Build.MANUFACTURER} ${Build.MODEL}")
        appendLine("识别方案：${RecognitionController.selectedEngine()}")
        appendLine("悬浮窗权限：${Settings.canDrawOverlays(this@MainActivity)}")
        appendLine("麦克风权限：${checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED}")
        appendLine("模型资源：")
        ModelResourceManager.states().forEach { state ->
            appendLine("- ${state.id}：${state.status}，版本=${state.version}，已存在=${state.presentBytes}/${state.totalBytes}")
        }
        append("日志位置：应用私有目录 files/logs/运行.log 与 files/logs/错误.log")
    }

    private fun initialStateJson(): JSONObject = JSONObject().apply {
        put("recognition", recognitionJson())
        put("settings", settingsJson())
        put("resources", resourcesJson(ModelResourceManager.states()))
        put("device", deviceJson())
        put("version", appVersion())
        put("page", currentPage)
    }

    private fun emitFullState() {
        emit(JSONObject().apply {
            put("type", "fullState")
            put("state", initialStateJson())
        })
    }

    private fun emitSettings() {
        emit(JSONObject().apply {
            put("type", "settings")
            put("settings", settingsJson())
        })
    }

    private fun emitHistory() {
        databaseExecutor.execute {
            val items = historyStore.list(500)
            emit(JSONObject().apply {
                put("type", "history")
                put("history", historyJson(items))
            })
        }
    }

    private fun emit(payload: JSONObject) {
        val encoded = JSONObject.quote(payload.toString())
        runOnUiThread {
            if (pageReady && ::webView.isInitialized) {
                webView.evaluateJavascript("window.VoiceApp.receive($encoded)", null)
            }
        }
    }

    private fun showMessage(message: String) {
        emit(JSONObject().apply {
            put("type", "toast")
            put("message", message)
        })
    }

    private fun recognitionJson(): JSONObject {
        val state = RecognitionController.snapshot()
        return JSONObject().apply {
            put("active", state.active)
            put("capturing", state.capturing)
            put("phase", state.phase)
            put("status", state.status)
            put("text", state.text)
        }
    }

    private fun settingsJson() = JSONObject().apply {
        put("engine", RecognitionController.selectedEngine())
        put("overlayEnabled", FloatingVoiceService.isRunning)
        put("overlayTextEnabled", OverlayPreferences.textEnabled(this@MainActivity))
        put("overlayOpacity", OverlayPreferences.opacity(this@MainActivity))
        put("overlaySize", OverlayPreferences.size(this@MainActivity))
        put("overlayPermission", Settings.canDrawOverlays(this@MainActivity))
        put(
            "microphonePermission",
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        )
    }

    private fun historyJson(items: List<HistoryItem>) = JSONArray().apply {
        items.forEach { item ->
            put(JSONObject().apply {
                put("id", item.id)
                put("text", item.text)
                put("createdAt", item.createdAt)
                put("engine", item.engine)
            })
        }
    }

    private fun resourcesJson(states: List<ModelResourceState>) = JSONArray().apply {
        states.forEach { state ->
            put(JSONObject().apply {
                put("id", state.id)
                put("name", state.name)
                put("purpose", state.purpose)
                put("version", state.version)
                put("totalBytes", state.totalBytes)
                put("presentBytes", state.presentBytes)
                put("installedBytes", state.installedBytes)
                put("status", state.status)
                put("speedBytesPerSecond", state.speedBytesPerSecond)
                put("etaSeconds", state.etaSeconds)
                put("freeBytes", state.freeBytes)
                put("errorMessage", state.errorMessage)
            })
        }
    }

    private fun deviceJson(): JSONObject {
        val info = ActivityManager.MemoryInfo()
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(info)
        val memoryGb = (info.totalMem / 1_073_741_824.0).roundToInt()
        val assessment = when {
            memoryGb >= 8 -> "适合使用推荐的双模型方案"
            memoryGb >= 6 -> "可以使用双模型，长时间录音时建议关闭其他大型应用"
            else -> "建议优先使用仅实时模型方案"
        }
        return JSONObject().apply {
            put("memoryGb", memoryGb)
            put("assessment", assessment)
        }
    }

    private fun appVersion(): String = runCatching {
        packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
    }.getOrDefault("")

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(STATE_PAGE, currentPage)
        super.onSaveInstanceState(outState)
    }

    override fun onBackPressed() {
        if (!pageReady || !::webView.isInitialized) {
            super.onBackPressed()
            return
        }
        webView.evaluateJavascript("window.VoiceApp.handleBack()") { handled ->
            if (handled != "true") super.onBackPressed()
        }
    }

    companion object {
        private const val REQUEST_AUDIO = 1001
        private const val REQUEST_NOTIFICATIONS = 1002
        private const val MAX_TEXT_LENGTH = 100_000
        private const val APP_ASSET_HOST = "appassets.androidplatform.net"
        private const val ENTRY_URL = "https://appassets.androidplatform.net/assets/web/index.html"
        private const val STATE_PAGE = "current-page"
        private val VALID_PAGES = setOf("recording", "history", "settings")
    }
}
