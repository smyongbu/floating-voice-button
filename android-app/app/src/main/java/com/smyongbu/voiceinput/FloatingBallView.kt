package com.smyongbu.voiceinput

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.provider.Settings
import android.view.View
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.exp
import kotlin.math.pow
import kotlin.math.sin

class FloatingBallView(context: Context) : View(context) {
    private val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(37, 99, 235)
    }
    private val iconPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = dp(2.2f)
        style = Paint.Style.STROKE
    }
    private val wavePaints = listOf(
        wavePaint(255, 1.8f),
        wavePaint(150, 1.35f),
        wavePaint(86, 1.05f)
    )
    private var active = false
    private var level = 0.06f
    private var targetLevel = 0.06f
    private var phase = 0f
    private var lastFrameNanos = 0L
    private val motionEnabled = runCatching {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f
    }.getOrDefault(true)
    private val animationFrame = object : Runnable {
        override fun run() {
            if (!active || !motionEnabled || !isAttachedToWindow) {
                lastFrameNanos = 0L
                return
            }
            val now = System.nanoTime()
            val elapsed = ((now - lastFrameNanos) / 1_000_000_000.0).coerceIn(0.0, 0.05)
            lastFrameNanos = now
            val smoothing = (1.0 - exp(-elapsed * 10.0)).toFloat()
            level += (targetLevel - level) * smoothing
            phase = (phase + (elapsed * 5.4).toFloat()) % (2f * PI.toFloat())
            invalidate()
            postOnAnimation(this)
        }
    }

    fun update(listening: Boolean, newLevel: Float) {
        targetLevel = max(0.04f, newLevel.coerceIn(0f, 1f))
        val started = listening && !active
        active = listening
        if (active && motionEnabled) {
            if (started || lastFrameNanos == 0L) {
                removeCallbacks(animationFrame)
                lastFrameNanos = System.nanoTime()
                postOnAnimation(animationFrame)
            }
        } else {
            removeCallbacks(animationFrame)
            lastFrameNanos = 0L
            level = targetLevel
        }
        invalidate()
    }

    override fun onDetachedFromWindow() {
        removeCallbacks(animationFrame)
        lastFrameNanos = 0L
        super.onDetachedFromWindow()
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val radius = minOf(width, height) / 2f
        canvas.drawCircle(width / 2f, height / 2f, radius, backgroundPaint)
        if (active) drawWave(canvas) else drawMicrophone(canvas)
    }

    private fun drawWave(canvas: Canvas) {
        val centerX = width / 2f
        val centerY = height / 2f
        val left = centerX - dp(18f)
        val waveWidth = dp(36f)
        val points = 18
        wavePaints.forEachIndexed { layer, paint ->
            val xs = FloatArray(points + 1)
            val ys = FloatArray(points + 1)
            for (index in 0..points) {
                val t = index.toFloat() / points
                val envelope = sin(PI * t).toFloat().coerceAtLeast(0f).pow(1.35f)
                val amplitude = dp(2.1f + level * 8.2f) * (1f - layer * 0.16f)
                val angle = phase + layer * 1.18f + t * (2f * PI.toFloat() * 1.28f)
                xs[index] = left + waveWidth * t
                ys[index] = centerY + sin(angle) * envelope * amplitude
            }
            val path = Path().apply {
                moveTo(xs[0], ys[0])
                for (index in 1 until points) {
                    val middleX = (xs[index] + xs[index + 1]) / 2f
                    val middleY = (ys[index] + ys[index + 1]) / 2f
                    quadTo(xs[index], ys[index], middleX, middleY)
                }
                quadTo(xs[points], ys[points], xs[points], ys[points])
            }
            canvas.drawPath(path, paint)
        }
    }

    private fun drawMicrophone(canvas: Canvas) {
        val centerX = width / 2f
        val centerY = height / 2f - dp(2f)
        iconPaint.strokeWidth = dp(2.2f)
        canvas.drawRoundRect(
            centerX - dp(5f),
            centerY - dp(11f),
            centerX + dp(5f),
            centerY + dp(5f),
            dp(5f),
            dp(5f),
            iconPaint
        )
        canvas.drawArc(
            centerX - dp(10f),
            centerY - dp(2f),
            centerX + dp(10f),
            centerY + dp(13f),
            0f,
            180f,
            false,
            iconPaint
        )
        canvas.drawLine(centerX, centerY + dp(13f), centerX, centerY + dp(19f), iconPaint)
        canvas.drawLine(
            centerX - dp(7f),
            centerY + dp(19f),
            centerX + dp(7f),
            centerY + dp(19f),
            iconPaint
        )
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val size = resolveSize(dp(58f).toInt(), widthMeasureSpec)
        setMeasuredDimension(size, size)
    }

    private fun wavePaint(alpha: Int, width: Float) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(alpha, 255, 255, 255)
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = dp(width)
    }

    private fun dp(value: Float) = value * resources.displayMetrics.density
}
