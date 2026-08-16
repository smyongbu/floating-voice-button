package com.smyongbu.voiceinput

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import kotlin.math.max

class WaveformView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(37,99,235); strokeCap = Paint.Cap.ROUND; strokeWidth = dp(3f) }
    private val levels = FloatArray(7) { 0.08f }
    fun setLevel(value: Float) {
        for (i in 0 until levels.lastIndex) levels[i] = levels[i + 1]
        levels[levels.lastIndex] = max(0.08f, value.coerceIn(0f, 1f)); invalidate()
    }
    fun reset() {
        levels.fill(0.08f)
        invalidate()
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas); val gap = width / 9f; val center = height / 2f
        for (i in levels.indices) { val h = dp(6f) + levels[i] * (height - dp(14f)); val x = gap * (i + 1.5f); canvas.drawLine(x, center - h/2, x, center + h/2, paint) }
    }
    private fun dp(v: Float) = v * resources.displayMetrics.density
}

class FloatingBallView(context: Context) : View(context) {
    private val blue = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(37,99,235) }
    private val white = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; strokeCap = Paint.Cap.ROUND; strokeWidth = dp(2.2f); style = Paint.Style.STROKE }
    private val bars = FloatArray(5) { 0.1f }; private var active = false
    fun update(listening: Boolean, level: Float) { active = listening; for(i in 0 until bars.lastIndex) bars[i]=bars[i+1]; bars[bars.lastIndex]=max(0.1f,level); invalidate() }
    override fun performClick(): Boolean { super.performClick(); return true }
    override fun onDraw(c: Canvas) {
        val r = minOf(width,height)/2f; c.drawCircle(width/2f,height/2f,r,blue)
        if(active){white.style=Paint.Style.STROKE;white.strokeWidth=dp(2f);val gap=dp(6f);val center=width/2f;for(i in bars.indices){val h=dp(7f)+bars[i]*dp(19f);val x=center+(i-2)*gap;c.drawLine(x,height/2f-h/2,x,height/2f+h/2,white)}}
        else {white.strokeWidth=dp(2.2f);val cx=width/2f;val cy=height/2f-dp(2f);c.drawRoundRect(cx-dp(5f),cy-dp(11f),cx+dp(5f),cy+dp(5f),dp(5f),dp(5f),white);c.drawArc(cx-dp(10f),cy-dp(2f),cx+dp(10f),cy+dp(13f),0f,180f,false,white);c.drawLine(cx,cy+dp(13f),cx,cy+dp(19f),white);c.drawLine(cx-dp(7f),cy+dp(19f),cx+dp(7f),cy+dp(19f),white)}
    }
    override fun onMeasure(w:Int,h:Int){val size=resolveSize(dp(58f).toInt(),w);setMeasuredDimension(size,size)}
    private fun dp(v:Float)=v*resources.displayMetrics.density
}
