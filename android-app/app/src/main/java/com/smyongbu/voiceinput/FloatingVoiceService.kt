package com.smyongbu.voiceinput

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.IntentFilter
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat

class FloatingVoiceService : Service(), RecognitionController.Listener {
    private data class SafeInsets(val left: Int, val top: Int, val right: Int, val bottom: Int)

    companion object {
        @Volatile var isRunning = false
        const val ACTION_STATE_CHANGED = "com.smyongbu.voiceinput.OVERLAY_STATE_CHANGED"
        const val ACTION_APPEARANCE_CHANGED = "com.smyongbu.voiceinput.OVERLAY_APPEARANCE_CHANGED"
        private const val CHANNEL = "悬浮语音输入"
    }

    private lateinit var windowManager: WindowManager
    private lateinit var ball: FloatingBallView
    private lateinit var logger: AppLogger
    private lateinit var caption: LinearLayout
    private lateinit var captionText: TextView
    private lateinit var ballParams: WindowManager.LayoutParams
    private lateinit var captionParams: WindowManager.LayoutParams
    private val handler = Handler(Looper.getMainLooper())
    private var capturing = false
    private var level = 0f
    private var lastText = ""
    private var ballSizeDp = OverlayPreferences.DEFAULT_SIZE
    private var toneGenerator: ToneGenerator? = null
    private val hideCaptionAction = Runnable {
        lastText = ""
        applyCaptionVisibility(false)
    }
    private val appearanceReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == ACTION_APPEARANCE_CHANGED) applyAppearance()
        }
    }

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        logger = AppLogger(this)
        RecognitionController.init(this)
        notifyForeground()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        ball = FloatingBallView(this).apply {
            contentDescription = "悬浮语音按钮。点击开始或停止，拖动改变位置，长按关闭。"
            elevation = dp(10).toFloat()
            isLongClickable = true
        }
        ball.setOpacityPercent(OverlayPreferences.opacity(this))
        captionText = TextView(this).apply {
            textSize = 13f
            setTextColor(Color.rgb(15, 23, 42))
            maxLines = 3
            includeFontPadding = false
            setPadding(dp(13), dp(11), dp(13), dp(11))
        }
        caption = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            elevation = dp(8).toFloat()
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                setColor(Color.argb(250, 255, 255, 255))
                setStroke(dp(1), Color.argb(230, 191, 219, 254))
            }
            addView(
                captionText,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
            )
            isClickable = true
            isFocusable = true
            contentDescription = "识别文字，点击复制"
        }
        caption.setOnClickListener { copyCaptionText() }
        toneGenerator = runCatching { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 48) }.getOrNull()
        ballSizeDp = OverlayPreferences.size(this)
        ballParams = params(dp(ballSizeDp), dp(ballSizeDp), WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE).apply {
            x = resources.displayMetrics.widthPixels - dp(78)
            y = resources.displayMetrics.heightPixels / 2
        }
        captionParams = params(
            resolveCaptionWidth(),
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        )
        try {
            windowManager.addView(caption, captionParams)
            windowManager.addView(ball, ballParams)
        } catch (error: Exception) {
            logger.error("创建悬浮窗口失败", error, "overlay-create")
            runCatching { if (caption.isAttachedToWindow) windowManager.removeView(caption) }
            isRunning = false
            stopSelf()
            return
        }
        applyCaptionVisibility(false)
        ContextCompat.registerReceiver(
            this,
            appearanceReceiver,
            IntentFilter(ACTION_APPEARANCE_CHANGED),
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
        attachGestures()
        RecognitionController.addListener(this)
        logger.info("悬浮语音按钮已启动", "overlay-start")
        broadcastState()
    }

    private fun params(width: Int, height: Int, flags: Int) = WindowManager.LayoutParams(
        width,
        height,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        flags,
        PixelFormat.TRANSLUCENT
    ).apply { gravity = Gravity.TOP or Gravity.START }

    private fun attachGestures() {
        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var moved = false
        var longPressed = false
        val closeAction = {
            RecognitionController.cancel()
            Toast.makeText(this, "悬浮小球已关闭。", Toast.LENGTH_SHORT).show()
            stopSelf()
            true
        }
        ball.setOnClickListener {
            val starting = !RecognitionController.isListening()
            ball.playTapFeedback()
            ball.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            playCue(starting)
            RecognitionController.toggle()
        }
        ball.setOnLongClickListener { closeAction() }
        var pending: Runnable? = null
        ball.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    startX = ballParams.x
                    startY = ballParams.y
                    moved = false
                    longPressed = false
                    pending = Runnable {
                        if (!moved) {
                            longPressed = true
                            ball.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                            ball.performLongClick()
                        }
                    }.also { handler.postDelayed(it, 700) }
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val x = (event.rawX - downX).toInt()
                    val y = (event.rawY - downY).toInt()
                    if (kotlin.math.abs(x) + kotlin.math.abs(y) > dp(6)) {
                        moved = true
                        pending?.let(handler::removeCallbacks)
                    }
                    if (!longPressed) {
                        ballParams.x = startX + x
                        ballParams.y = startY + y
                        clampBallPosition()
                        moveCaption()
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    pending?.let(handler::removeCallbacks)
                    if (!moved && !longPressed) ball.performClick()
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    pending?.let(handler::removeCallbacks)
                    true
                }
                else -> false
            }
        }
    }

    private fun moveCaption() {
        val screenWidth = resources.displayMetrics.widthPixels
        val screenHeight = resources.displayMetrics.heightPixels
        val safe = systemInsets()
        val minX = dp(8) + safe.left
        val maxX = (screenWidth - captionParams.width - dp(8) - safe.right).coerceAtLeast(minX)
        val gap = dp(10)
        val left = ballParams.x - captionParams.width - gap
        val right = ballParams.x + dp(ballSizeDp) + gap
        caption.measure(
            View.MeasureSpec.makeMeasureSpec(captionParams.width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED)
        )
        val captionHeight = caption.measuredHeight.coerceAtLeast(dp(42))
        val minY = dp(8) + safe.top
        val maxY = (screenHeight - captionHeight - dp(8) - safe.bottom).coerceAtLeast(minY)
        val canFitLeft = left >= minX
        val canFitRight = right <= maxX
        if (canFitLeft || canFitRight) {
            captionParams.x = if (canFitLeft) left else right
            captionParams.y = (ballParams.y + (dp(ballSizeDp) - captionHeight) / 2).coerceIn(minY, maxY)
        } else {
            captionParams.x = (ballParams.x + (dp(ballSizeDp) - captionParams.width) / 2)
                .coerceIn(minX, maxX)
            val above = ballParams.y - captionHeight - gap
            val below = ballParams.y + dp(ballSizeDp) + gap
            captionParams.y = if (above >= minY) above else below.coerceIn(minY, maxY)
        }
        safeUpdate(caption, captionParams)
    }

    private fun clampBallPosition() {
        val margin = dp(4)
        val safe = systemInsets()
        val minX = margin + safe.left
        val minY = margin + safe.top
        val maxX = (resources.displayMetrics.widthPixels - dp(ballSizeDp) - margin - safe.right)
            .coerceAtLeast(minX)
        val maxY = (resources.displayMetrics.heightPixels - dp(ballSizeDp) - margin - safe.bottom)
            .coerceAtLeast(minY)
        ballParams.x = ballParams.x.coerceIn(minX, maxX)
        ballParams.y = ballParams.y.coerceIn(minY, maxY)
        safeUpdate(ball, ballParams)
    }

    private fun systemInsets(): SafeInsets = if (Build.VERSION.SDK_INT >= 30) {
        val value = windowManager.currentWindowMetrics.windowInsets.getInsetsIgnoringVisibility(
            WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout()
        )
        SafeInsets(value.left, value.top, value.right, value.bottom)
    } else SafeInsets(0, 0, 0, 0)

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        handler.post {
            captionParams.width = resolveCaptionWidth()
            clampBallPosition()
            moveCaption()
        }
    }

    private fun applyCaptionVisibility(show: Boolean) {
        val visible = show && OverlayPreferences.textEnabled(this)
        caption.visibility = if (visible) View.VISIBLE else View.GONE
        captionParams.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        safeUpdate(caption, captionParams)
        if (visible) moveCaption()
    }

    private fun playCue(starting: Boolean) {
        val tone = if (starting) ToneGenerator.TONE_PROP_BEEP2 else ToneGenerator.TONE_PROP_ACK
        runCatching { toneGenerator?.startTone(tone, 145) }
            .onFailure { logger.error("播放悬浮球提示音失败", it, "overlay-cue") }
    }

    private fun copyCaptionText() {
        val value = lastText.trim()
        if (value.isEmpty()) return
        handler.removeCallbacks(hideCaptionAction)
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("识别文字", value))
        captionText.text = "已复制"
        applyCaptionVisibility(true)
        handler.postDelayed(hideCaptionAction, 1_000L)
        logger.info("已从悬浮文字框复制识别文字", "overlay-copy")
    }

    private fun applyAppearance() {
        ball.setOpacityPercent(OverlayPreferences.opacity(this))
        val nextSizeDp = OverlayPreferences.size(this)
        if (nextSizeDp != ballSizeDp) {
            ballSizeDp = nextSizeDp
            ballParams.width = dp(ballSizeDp)
            ballParams.height = dp(ballSizeDp)
            captionParams.width = resolveCaptionWidth()
            clampBallPosition()
            moveCaption()
        }
        applyCaptionVisibility(RecognitionController.isListening() || lastText.isNotBlank())
    }

    private fun safeUpdate(view: View, params: WindowManager.LayoutParams) {
        if (!view.isAttachedToWindow) return
        try {
            windowManager.updateViewLayout(view, params)
        } catch (error: Exception) {
            logger.error("更新悬浮窗口失败", error, "overlay-update")
            stopSelf()
        }
    }

    override fun onRecognitionState(listening: Boolean, status: String, text: String) {
        handler.post {
            val active = RecognitionController.isListening()
            capturing = listening
            lastText = text
            ball.update(capturing, level)
            captionText.text = text.ifBlank { status }
            handler.removeCallbacks(hideCaptionAction)
            when {
                active -> applyCaptionVisibility(true)
                text.isNotBlank() -> {
                    applyCaptionVisibility(true)
                    handler.postDelayed(hideCaptionAction, 2_000L)
                }
                else -> applyCaptionVisibility(false)
            }
        }
    }

    private fun resolveCaptionWidth(): Int {
        val available = resources.displayMetrics.widthPixels - dp(ballSizeDp) - dp(36)
        return minOf(dp(220), available).coerceAtLeast(dp(180))
    }

    override fun onAudioLevel(level: Float) {
        handler.post {
            this.level = level
            ball.update(capturing, level)
        }
    }

    private fun notifyForeground() {
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(
            NotificationChannel(CHANNEL, "悬浮语音输入", NotificationManager.IMPORTANCE_LOW)
        )
        val intent = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val open = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        startForeground(
            7,
            Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.app_icon)
                .setContentTitle("悬浮语音输入正在运行")
                .setContentText("点击开始或停止，长按关闭悬浮球")
                .setContentIntent(open)
                .build()
        )
    }

    private fun broadcastState() {
        sendBroadcast(
            Intent(ACTION_STATE_CHANGED)
                .setPackage(packageName)
                .putExtra("running", isRunning)
        )
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        toneGenerator?.release()
        toneGenerator = null
        runCatching { unregisterReceiver(appearanceReceiver) }
        RecognitionController.removeListener(this)
        if (::ball.isInitialized) runCatching {
            if (ball.isAttachedToWindow) windowManager.removeView(ball)
        }
        if (::caption.isInitialized) runCatching {
            if (caption.isAttachedToWindow) windowManager.removeView(caption)
        }
        isRunning = false
        broadcastState()
        logger.info("悬浮语音按钮已关闭", "overlay-stop")
        super.onDestroy()
    }
}
