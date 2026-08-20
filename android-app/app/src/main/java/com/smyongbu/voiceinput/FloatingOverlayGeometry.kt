package com.smyongbu.voiceinput

import kotlin.math.abs
import kotlin.math.roundToInt

internal object FloatingOverlayGeometry {
    enum class Side { LEFT, RIGHT }

    data class Bounds(
        val minX: Int,
        val maxX: Int,
        val minY: Int,
        val maxY: Int,
    )

    data class StoredPosition(
        val side: Side,
        val normalizedY: Float,
    )

    fun bounds(
        screenWidth: Int,
        screenHeight: Int,
        ballSize: Int,
        margin: Int,
        insetLeft: Int,
        insetTop: Int,
        insetRight: Int,
        insetBottom: Int,
    ): Bounds {
        val minX = margin + insetLeft
        val minY = margin + insetTop
        return Bounds(
            minX = minX,
            maxX = (screenWidth - ballSize - margin - insetRight).coerceAtLeast(minX),
            minY = minY,
            maxY = (screenHeight - ballSize - margin - insetBottom).coerceAtLeast(minY),
        )
    }

    fun nearestSide(x: Int, bounds: Bounds): Side {
        val leftDistance = abs(x - bounds.minX)
        val rightDistance = abs(bounds.maxX - x)
        return if (leftDistance <= rightDistance) Side.LEFT else Side.RIGHT
    }

    fun xForSide(side: Side, bounds: Bounds): Int = when (side) {
        Side.LEFT -> bounds.minX
        Side.RIGHT -> bounds.maxX
    }

    fun normalizedY(y: Int, bounds: Bounds): Float {
        val range = bounds.maxY - bounds.minY
        if (range <= 0) return 0.5f
        return ((y.coerceIn(bounds.minY, bounds.maxY) - bounds.minY).toFloat() / range)
            .coerceIn(0f, 1f)
    }

    fun yFromNormalized(normalizedY: Float, bounds: Bounds): Int {
        val progress = normalizedY.coerceIn(0f, 1f)
        return (bounds.minY + (bounds.maxY - bounds.minY) * progress)
            .roundToInt()
            .coerceIn(bounds.minY, bounds.maxY)
    }

    fun easeOutCubic(progress: Float): Float {
        val value = progress.coerceIn(0f, 1f)
        val remaining = 1f - value
        return 1f - remaining * remaining * remaining
    }

    fun interpolate(start: Int, end: Int, progress: Float): Int =
        (start + (end - start) * progress.coerceIn(0f, 1f)).roundToInt()
}
