package com.smyongbu.voiceinput

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.IntentFilter
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
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
import android.widget.Button
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
    private var manuallyHidden = false
    private var previousActive = false
    private var lastText = ""
    private var ballSizeDp = OverlayPreferences.DEFAULT_SIZE
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
            textSize = 15f
            setTextColor(Color.rgb(15, 23, 42))
            maxLines = 3
            setPadding(dp(12), dp(8), dp(8), dp(8))
        }
        val close = Button(this).apply {
            text = "关闭"
            isAllCaps = false
            textSize = 12f
            contentDescription = "关闭悬浮文字"
            setTextColor(Color.rgb(71, 85, 105))
            background = getDrawable(R.drawable.secondary_button)
            setOnClickListener {
                manuallyHidden = true
                applyCaptionVisibility(false)
            }
        }
        caption = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = GradientDrawable().apply {
                cornerRadius = dp(12).toFloat()
                setColor(Color.argb(246, 255, 255, 255))
                setStroke(dp(1), Color.rgb(215, 224, 236))
            }
            addView(captionText, LinearLayout.LayoutParams(0, WindowManager.LayoutParams.WRAP_CONTENT, 1f))
            addView(close, LinearLayout.LayoutParams(dp(64), dp(48)).apply { marginEnd = dp(6) })
        }
        ballSizeDp = OverlayPreferences.size(this)
        ballParams = params(dp(ballSizeDp), dp(ballSizeDp), WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE).apply {
            x = resources.displayMetrics.widthPixels - dp(78)
            y = resources.displayMetrics.heightPixels / 2
        }
        val captionWidth = minOf(dp(330), resources.displayMetrics.widthPixels - dp(16)).coerceAtLeast(dp(220))
        captionParams = params(
            captionWidth,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
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
        ball.setOnClickListener { RecognitionController.toggle() }
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
        val safe = systemInsets()
        val minX = dp(8) + safe.left
        val maxX = (screenWidth - captionParams.width - dp(8) - safe.right).coerceAtLeast(minX)
        captionParams.x = (ballParams.x - captionParams.width + dp(ballSizeDp)).coerceIn(
            minX,
            maxX
        )
        captionParams.y = (ballParams.y - dp(94)).coerceAtLeast(dp(8) + safe.top)
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
            captionParams.width = minOf(dp(330), resources.displayMetrics.widthPixels - dp(16))
                .coerceAtLeast(dp(220))
            clampBallPosition()
            moveCaption()
        }
    }

    private fun applyCaptionVisibility(show: Boolean) {
        val visible = show && OverlayPreferences.textEnabled(this)
        caption.visibility = if (visible) View.VISIBLE else View.GONE
        captionParams.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            (if (visible) 0 else WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)
        safeUpdate(caption, captionParams)
        if (visible) moveCaption()
    }

    private fun applyAppearance() {
        ball.setOpacityPercent(OverlayPreferences.opacity(this))
        val nextSizeDp = OverlayPreferences.size(this)
        if (nextSizeDp != ballSizeDp) {
            ballSizeDp = nextSizeDp
            ballParams.width = dp(ballSizeDp)
            ballParams.height = dp(ballSizeDp)
            clampBallPosition()
            moveCaption()
        }
        applyCaptionVisibility(!manuallyHidden && (RecognitionController.isListening() || lastText.isNotBlank()))
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
            if (active && !previousActive) manuallyHidden = false
            previousActive = active
            capturing = listening
            lastText = text
            ball.update(capturing, level)
            captionText.text = text.ifBlank { status }
            applyCaptionVisibility(!manuallyHidden && (active || text.isNotBlank()))
        }
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
