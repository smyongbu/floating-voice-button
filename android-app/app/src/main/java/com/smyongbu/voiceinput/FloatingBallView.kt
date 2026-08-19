package com.smyongbu.voiceinput

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.Shader
import android.provider.Settings
import android.view.View
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

internal object FloatingWaveMath {
    const val RECORDING_AMPLITUDE = 0.42f
    const val RECORDING_SPEED = 0.065f

    fun targetAmplitude(rawLevel: Float): Float {
        val voice = rawLevel.coerceIn(0f, 1f).toDouble().pow(0.65).toFloat()
        return 0.1f + 0.78f * voice
    }

    fun targetSpeed(rawLevel: Float): Float {
        val voice = rawLevel.coerceIn(0f, 1f).toDouble().pow(0.65).toFloat()
        return 0.045f + 0.0725f * voice
    }

    fun phaseRadiansPerMillisecond(speed: Float): Float = 0.0022f + speed * 0.0255f
    fun amplitudeUnits(level: Float): Float = 2f + level * 18.5f

    fun smooth(current: Float, target: Float, elapsedSeconds: Float, timeConstant: Float): Float {
        if (elapsedSeconds <= 0f) return current
        val factor = (1.0 - exp((-elapsedSeconds / timeConstant).toDouble())).toFloat()
        return current + (target - current) * factor
    }

    fun smoothStep(value: Float): Float {
        val clamped = value.coerceIn(0f, 1f)
        return clamped * clamped * (3f - 2f * clamped)
    }

    fun sample(ratio: Float, cycles: Float, phase: Float): Float {
        val envelope = sin(PI * ratio).coerceAtLeast(0.0).pow(1.65)
        val harmonic = sin(ratio * PI * 2.0 * cycles + phase)
        val detail = sin(ratio * PI * 2.0 * (cycles * 1.9) - phase * 0.6) * 0.17
        return ((harmonic + detail) * envelope).toFloat()
    }
}

class FloatingBallView(context: Context) : View(context) {
    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1.15f)
    }
    private val standbyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(107, 114, 128)
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = dp(1.65f)
    }
    private val waveGlowPaint = wavePaint(dp(3.6f), 150, Color.WHITE)
    private val waveBackPaint = wavePaint(dp(1.15f), 255)
    private val waveMiddlePaint = wavePaint(dp(1.45f), 224)
    private val waveFrontPaint = wavePaint(dp(2.05f), 255)
    private val waveBackPath = Path()
    private val waveMiddlePath = Path()
    private val waveFrontPath = Path()
    private val pointX = FloatArray(37)
    private val pointY = FloatArray(37)

    private var active = false
    private var currentAmplitude = FloatingWaveMath.RECORDING_AMPLITUDE
    private var targetAmplitude = FloatingWaveMath.RECORDING_AMPLITUDE
    private var currentSpeed = FloatingWaveMath.RECORDING_SPEED
    private var targetSpeed = FloatingWaveMath.RECORDING_SPEED
    private var shapeMix = 0f
    private var shapeFrom = 0f
    private var shapeTarget = 0f
    private var shapeStartedNanos = 0L
    private var shapeDurationNanos = 280_000_000L
    private var phase = 0f
    private var lastFrameNanos = 0L
    private var animationScheduled = false
    private var waveLeft = 0f
    private var waveWidth = 0f
    private var waveHeight = 0f
    private val motionEnabled = runCatching {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f
    }.getOrDefault(true)

    private val animationFrame = object : Runnable {
        override fun run() {
            animationScheduled = false
            if (!motionEnabled || !isAttachedToWindow) {
                lastFrameNanos = 0L
                return
            }
            val now = System.nanoTime()
            if (lastFrameNanos == 0L) lastFrameNanos = now
            val elapsedSeconds = ((now - lastFrameNanos) / 1_000_000_000.0).coerceIn(0.0, 0.08).toFloat()
            lastFrameNanos = now
            if (shapeMix != shapeTarget) {
                val progress = ((now - shapeStartedNanos).toDouble() / shapeDurationNanos).toFloat().coerceIn(0f, 1f)
                shapeMix = shapeFrom + (shapeTarget - shapeFrom) * FloatingWaveMath.smoothStep(progress)
                if (progress >= 1f) shapeMix = shapeTarget
            }
            if (active) {
                val timeConstant = if (targetAmplitude > currentAmplitude) 0.045f else 0.22f
                currentAmplitude = FloatingWaveMath.smooth(currentAmplitude, targetAmplitude, elapsedSeconds, timeConstant)
                currentSpeed = FloatingWaveMath.smooth(currentSpeed, targetSpeed, elapsedSeconds, 0.14f)
                phase = (phase + elapsedSeconds * 1_000f * FloatingWaveMath.phaseRadiansPerMillisecond(currentSpeed) * shapeMix) % (2f * PI.toFloat())
            }
            invalidate()
            if (active || shapeMix != shapeTarget) scheduleAnimation() else lastFrameNanos = 0L
        }
    }

    fun update(listening: Boolean, newLevel: Float) {
        val changed = listening != active
        active = listening
        if (active) {
            if (changed) {
                currentAmplitude = FloatingWaveMath.RECORDING_AMPLITUDE
                currentSpeed = FloatingWaveMath.RECORDING_SPEED
            }
            targetAmplitude = FloatingWaveMath.targetAmplitude(newLevel)
            targetSpeed = FloatingWaveMath.targetSpeed(newLevel)
        }
        if (changed) setShapeTarget(if (active) 1f else 0f)
        if (!motionEnabled) {
            shapeMix = shapeTarget
            stopAnimation()
        } else if (active || shapeMix != shapeTarget) scheduleAnimation()
        invalidate()
    }

    fun playTapFeedback() {
        if (!motionEnabled) return
        animate().cancel()
        scaleX = 1f
        scaleY = 1f
        animate().scaleX(1.065f).scaleY(1.065f).setDuration(70L).withEndAction {
            animate().scaleX(1f).scaleY(1f).setDuration(110L).start()
        }.start()
    }

    private fun setShapeTarget(target: Float) {
        if (!motionEnabled) {
            shapeMix = target
            shapeFrom = target
            shapeTarget = target
            return
        }
        shapeFrom = shapeMix
        shapeTarget = target
        shapeStartedNanos = System.nanoTime()
        shapeDurationNanos = (280_000_000L * kotlin.math.abs(shapeTarget - shapeFrom)).toLong().coerceAtLeast(100_000_000L)
    }

    fun setOpacityPercent(percent: Int) {
        val fraction = percent.coerceIn(35, 100) / 100f
        alpha = fraction
        elevation = dp(10f) * fraction
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        invalidate()
    }

    override fun onDetachedFromWindow() {
        stopAnimation()
        animate().cancel()
        super.onDetachedFromWindow()
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        super.onSizeChanged(width, height, oldWidth, oldHeight)
        val size = min(width, height).toFloat()
        val centerX = width / 2f
        val centerY = height / 2f
        val radius = size / 2f
        waveWidth = size * 0.8462f
        waveHeight = size * 0.5077f
        waveLeft = centerX - waveWidth / 2f
        glowPaint.shader = RadialGradient(centerX, centerY, radius,
            intArrayOf(Color.TRANSPARENT, Color.TRANSPARENT, Color.argb(238, 103, 232, 249), Color.argb(184, 37, 99, 235), Color.TRANSPARENT),
            floatArrayOf(0f, 0.68f, 0.82f, 0.93f, 1f), Shader.TileMode.CLAMP)
        backgroundPaint.shader = LinearGradient(centerX - radius, centerY - radius, centerX + radius, centerY + radius,
            intArrayOf(Color.argb(252, 255, 255, 255), Color.argb(248, 248, 251, 255), Color.argb(242, 224, 239, 255)),
            floatArrayOf(0f, 0.54f, 1f), Shader.TileMode.CLAMP)
        highlightPaint.shader = RadialGradient(centerX - radius * 0.32f, centerY - radius * 0.36f, radius * 0.72f,
            intArrayOf(Color.argb(246, 255, 255, 255), Color.argb(92, 255, 255, 255), Color.TRANSPARENT),
            floatArrayOf(0f, 0.38f, 1f), Shader.TileMode.CLAMP)
        waveBackPaint.shader = LinearGradient(waveLeft, centerY, waveLeft + waveWidth, centerY,
            intArrayOf(Color.argb(0, 219, 234, 254), Color.rgb(186, 230, 253), Color.rgb(125, 211, 252), Color.argb(0, 219, 234, 254)),
            floatArrayOf(0f, 0.22f, 0.78f, 1f), Shader.TileMode.CLAMP)
        waveMiddlePaint.shader = LinearGradient(waveLeft, centerY, waveLeft + waveWidth, centerY,
            intArrayOf(Color.argb(0, 125, 211, 252), Color.rgb(125, 211, 252), Color.rgb(34, 211, 238), Color.rgb(56, 189, 248), Color.argb(0, 125, 211, 252)),
            floatArrayOf(0f, 0.2f, 0.52f, 0.82f, 1f), Shader.TileMode.CLAMP)
        waveFrontPaint.shader = LinearGradient(waveLeft, centerY, waveLeft + waveWidth, centerY,
            intArrayOf(Color.argb(0, 59, 130, 246), Color.rgb(37, 99, 235), Color.rgb(6, 182, 212), Color.rgb(37, 99, 235), Color.argb(0, 59, 130, 246)),
            floatArrayOf(0f, 0.16f, 0.5f, 0.84f, 1f), Shader.TileMode.CLAMP)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val size = min(width, height).toFloat()
        val centerX = width / 2f
        val centerY = height / 2f
        val radius = size / 2f
        if (shapeMix > 0f) {
            val pulse = 0.88f + 0.12f * ((sin(phase.toDouble()) + 1.0) / 2.0).toFloat()
            glowPaint.alpha = (255f * shapeMix * pulse).toInt().coerceIn(0, 255)
            canvas.drawCircle(centerX, centerY, radius - dp(0.2f), glowPaint)
        }
        canvas.drawCircle(centerX, centerY, radius - dp(0.65f), backgroundPaint)
        canvas.drawCircle(centerX, centerY, radius - dp(0.8f), highlightPaint)
        borderPaint.color = Color.argb(230, 191, 219, 254)
        canvas.drawCircle(centerX, centerY, radius - dp(0.65f), borderPaint)
        drawMorph(canvas, centerX, centerY)
    }

    private fun drawMorph(canvas: Canvas, centerX: Float, centerY: Float) {
        val amplitude = FloatingWaveMath.amplitudeUnits(currentAmplitude) * waveHeight / 72f
        buildMorphPath(waveBackPath, centerX, centerY, amplitude * 0.43f, 2.9f, -phase * 0.82f, 0)
        buildMorphPath(waveMiddlePath, centerX, centerY, amplitude * 0.68f, 1.82f, phase * 0.64f + 0.7f, 1)
        buildMorphPath(waveFrontPath, centerX, centerY, amplitude, 2.25f, phase, 2)
        standbyPaint.alpha = ((1f - shapeMix) * 255f).toInt().coerceIn(0, 255)
        if (standbyPaint.alpha > 0) {
            canvas.drawPath(waveMiddlePath, standbyPaint)
            canvas.drawPath(waveFrontPath, standbyPaint)
        }
        waveBackPaint.alpha = (255f * shapeMix).toInt().coerceIn(0, 255)
        waveMiddlePaint.alpha = (224f * shapeMix).toInt().coerceIn(0, 224)
        waveFrontPaint.alpha = (255f * shapeMix).toInt().coerceIn(0, 255)
        waveGlowPaint.alpha = (150f * shapeMix).toInt().coerceIn(0, 150)
        if (shapeMix > 0f) {
            canvas.drawPath(waveBackPath, waveBackPaint)
            canvas.drawPath(waveMiddlePath, waveMiddlePaint)
            canvas.drawPath(waveFrontPath, waveGlowPaint)
            canvas.drawPath(waveFrontPath, waveFrontPaint)
        }
    }

    private fun buildMorphPath(path: Path, centerX: Float, centerY: Float, amplitude: Float, cycles: Float, layerPhase: Float, layer: Int) {
        path.reset()
        val standbyRadius = waveWidth * (22f / 120f)
        for (index in 0..36) {
            val ratio = index / 36f
            val waveX = waveLeft + waveWidth * ratio
            val waveY = centerY + FloatingWaveMath.sample(ratio, cycles, layerPhase) * amplitude
            val angle = when (layer) { 1 -> PI + ratio * PI; 2 -> PI - ratio * PI; else -> 0.0 }
            val standbyX = if (layer == 0) centerX - standbyRadius + standbyRadius * 2f * ratio else centerX + cos(angle).toFloat() * standbyRadius
            val standbyY = if (layer == 0) centerY else centerY + sin(angle).toFloat() * standbyRadius
            pointX[index] = standbyX + (waveX - standbyX) * shapeMix
            pointY[index] = standbyY + (waveY - standbyY) * shapeMix
        }
        path.moveTo(pointX[0], pointY[0])
        for (index in 1 until 36) {
            path.quadTo(pointX[index], pointY[index], (pointX[index] + pointX[index + 1]) / 2f, (pointY[index] + pointY[index + 1]) / 2f)
        }
        path.lineTo(pointX[36], pointY[36])
    }

    private fun scheduleAnimation() {
        if (animationScheduled || !motionEnabled || !isAttachedToWindow || (!active && shapeMix == shapeTarget)) return
        animationScheduled = true
        postOnAnimation(animationFrame)
    }

    private fun stopAnimation() {
        removeCallbacks(animationFrame)
        animationScheduled = false
        lastFrameNanos = 0L
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desired = dp(OverlayPreferences.DEFAULT_SIZE.toFloat()).toInt()
        val measuredWidth = resolveSize(desired, widthMeasureSpec)
        val measuredHeight = resolveSize(desired, heightMeasureSpec)
        val size = min(measuredWidth, measuredHeight)
        setMeasuredDimension(size, size)
    }

    private fun wavePaint(width: Float, alpha: Int, color: Int? = null) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        this.alpha = alpha
        if (color != null) this.color = color
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = width
    }

    private fun dp(value: Float) = value * resources.displayMetrics.density
}
