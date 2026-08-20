package com.smyongbu.voiceinput

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.TimeInterpolator
import android.animation.ValueAnimator
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
    private var snapAnimator: ValueAnimator? = null
    private var attachedSide = FloatingOverlayGeometry.Side.RIGHT
    private var restorablePosition = FloatingOverlayGeometry.StoredPosition(attachedSide, 0.5f)
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
            contentDescription = "悬浮语音按钮。点击开始或停止，拖动后松手贴边，长按关闭。"
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
            restorablePosition = OverlayPreferences.position(this@FloatingVoiceService)
                ?: FloatingOverlayGeometry.StoredPosition(FloatingOverlayGeometry.Side.RIGHT, 0.5f)
            attachedSide = restorablePosition.side
            val bounds = ballBounds()
            x = FloatingOverlayGeometry.xForSide(attachedSide, bounds)
            y = FloatingOverlayGeometry.yFromNormalized(restorablePosition.normalizedY, bounds)
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
                    cancelSnapAnimation()
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
                        clampBallPosition(updateSide = true)
                        moveCaption()
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    pending?.let(handler::removeCallbacks)
                    when {
                        !moved && !longPressed -> {
                            ball.performClick()
                            settleBallIfNeeded()
                        }
                        moved && !longPressed -> snapBallToNearestEdge()
                    }
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    pending?.let(handler::removeCallbacks)
                    if (!longPressed) settleBallIfNeeded()
                    true
                }
                else -> false
            }
        }
    }

    private fun moveCaption() {
        val (screenWidth, screenHeight) = screenSize()
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
        val preferredX = when (attachedSide) {
            FloatingOverlayGeometry.Side.LEFT -> right
            FloatingOverlayGeometry.Side.RIGHT -> left
        }
        if (preferredX in minX..maxX) {
            captionParams.x = preferredX
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

    private fun clampBallPosition(updateSide: Boolean = false) {
        val bounds = ballBounds()
        ballParams.x = ballParams.x.coerceIn(bounds.minX, bounds.maxX)
        ballParams.y = ballParams.y.coerceIn(bounds.minY, bounds.maxY)
        if (updateSide) attachedSide = FloatingOverlayGeometry.nearestSide(ballParams.x, bounds)
        safeUpdate(ball, ballParams)
    }

    private fun ballBounds(): FloatingOverlayGeometry.Bounds {
        val safe = systemInsets()
        val (screenWidth, screenHeight) = screenSize()
        return FloatingOverlayGeometry.bounds(
            screenWidth = screenWidth,
            screenHeight = screenHeight,
            ballSize = dp(ballSizeDp),
            margin = dp(4),
            insetLeft = safe.left,
            insetTop = safe.top,
            insetRight = safe.right,
            insetBottom = safe.bottom,
        )
    }

    private fun screenSize(): Pair<Int, Int> = if (Build.VERSION.SDK_INT >= 30) {
        val bounds = windowManager.currentWindowMetrics.bounds
        bounds.width() to bounds.height()
    } else {
        resources.displayMetrics.widthPixels to resources.displayMetrics.heightPixels
    }

    private fun snapBallToNearestEdge() {
        cancelSnapAnimation()
        val bounds = ballBounds()
        attachedSide = FloatingOverlayGeometry.nearestSide(ballParams.x, bounds)
        restorablePosition = FloatingOverlayGeometry.StoredPosition(
            side = attachedSide,
            normalizedY = FloatingOverlayGeometry.normalizedY(ballParams.y, bounds),
        )
        OverlayPreferences.setPosition(this, restorablePosition)
        val startX = ballParams.x
        val startY = ballParams.y
        val targetX = FloatingOverlayGeometry.xForSide(attachedSide, bounds)
        val targetY = FloatingOverlayGeometry.yFromNormalized(restorablePosition.normalizedY, bounds)
        if (startX == targetX || !ValueAnimator.areAnimatorsEnabled()) {
            placeBall(targetX, targetY)
            logSnapCompleted()
            return
        }
        val animator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 200L
            interpolator = TimeInterpolator { progress ->
                FloatingOverlayGeometry.easeOutCubic(progress)
            }
            addUpdateListener { value ->
                val progress = value.animatedValue as Float
                placeBall(
                    FloatingOverlayGeometry.interpolate(startX, targetX, progress),
                    FloatingOverlayGeometry.interpolate(startY, targetY, progress),
                )
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    if (snapAnimator !== animation) return
                    snapAnimator = null
                    placeBall(targetX, targetY)
                    logSnapCompleted()
                }
            })
        }
        snapAnimator = animator
        animator.start()
    }

    private fun settleBallIfNeeded() {
        val bounds = ballBounds()
        val targetX = FloatingOverlayGeometry.xForSide(
            FloatingOverlayGeometry.nearestSide(ballParams.x, bounds),
            bounds,
        )
        if (ballParams.x != targetX) snapBallToNearestEdge()
    }

    private fun placeBall(x: Int, y: Int) {
        ballParams.x = x
        ballParams.y = y
        safeUpdate(ball, ballParams)
        moveCaption()
    }

    private fun cancelSnapAnimation() {
        val running = snapAnimator ?: return
        snapAnimator = null
        running.cancel()
    }

    private fun logSnapCompleted() {
        val side = if (attachedSide == FloatingOverlayGeometry.Side.LEFT) "左侧" else "右侧"
        logger.info("悬浮球已吸附到${side}安全边缘", "overlay-snap")
    }

    private fun restoreBallPosition() {
        attachedSide = restorablePosition.side
        val bounds = ballBounds()
        placeBall(
            FloatingOverlayGeometry.xForSide(attachedSide, bounds),
            FloatingOverlayGeometry.yFromNormalized(restorablePosition.normalizedY, bounds),
        )
    }

    private fun systemInsets(): SafeInsets = if (Build.VERSION.SDK_INT >= 30) {
        val value = windowManager.currentWindowMetrics.windowInsets.getInsetsIgnoringVisibility(
            WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout()
        )
        SafeInsets(value.left, value.top, value.right, value.bottom)
    } else SafeInsets(0, 0, 0, 0)

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        cancelSnapAnimation()
        handler.post {
            captionParams.width = resolveCaptionWidth()
            restoreBallPosition()
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
            cancelSnapAnimation()
            val oldBounds = ballBounds()
            restorablePosition = FloatingOverlayGeometry.StoredPosition(
                side = attachedSide,
                normalizedY = FloatingOverlayGeometry.normalizedY(ballParams.y, oldBounds),
            )
            ballSizeDp = nextSizeDp
            ballParams.width = dp(ballSizeDp)
            ballParams.height = dp(ballSizeDp)
            captionParams.width = resolveCaptionWidth()
            OverlayPreferences.setPosition(this, restorablePosition)
            restoreBallPosition()
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
        val available = screenSize().first - dp(ballSizeDp) - dp(36)
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
        cancelSnapAnimation()
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
