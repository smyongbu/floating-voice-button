package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FloatingOverlayGeometryTest {
    private val bounds = FloatingOverlayGeometry.bounds(
        screenWidth = 1080,
        screenHeight = 2400,
        ballSize = 168,
        margin = 12,
        insetLeft = 0,
        insetTop = 72,
        insetRight = 0,
        insetBottom = 96,
    )

    @Test
    fun nearestSideUsesTheClosestSafeEdge() {
        assertEquals(FloatingOverlayGeometry.Side.LEFT, FloatingOverlayGeometry.nearestSide(120, bounds))
        assertEquals(FloatingOverlayGeometry.Side.RIGHT, FloatingOverlayGeometry.nearestSide(760, bounds))
        assertEquals(bounds.minX, FloatingOverlayGeometry.xForSide(FloatingOverlayGeometry.Side.LEFT, bounds))
        assertEquals(bounds.maxX, FloatingOverlayGeometry.xForSide(FloatingOverlayGeometry.Side.RIGHT, bounds))
    }

    @Test
    fun normalizedHeightRestoresTheSameRelativePositionAfterRotation() {
        val originalY = FloatingOverlayGeometry.yFromNormalized(0.72f, bounds)
        val savedY = FloatingOverlayGeometry.normalizedY(originalY, bounds)
        val rotated = FloatingOverlayGeometry.bounds(
            screenWidth = 2400,
            screenHeight = 1080,
            ballSize = 168,
            margin = 12,
            insetLeft = 72,
            insetTop = 0,
            insetRight = 96,
            insetBottom = 0,
        )
        val restoredY = FloatingOverlayGeometry.yFromNormalized(savedY, rotated)

        assertEquals(0.72f, FloatingOverlayGeometry.normalizedY(restoredY, rotated), 0.002f)
        assertTrue(restoredY in rotated.minY..rotated.maxY)
    }

    @Test
    fun cubicEaseOutStartsQuicklyAndKeepsExactEndpoints() {
        assertEquals(0f, FloatingOverlayGeometry.easeOutCubic(0f), 0f)
        assertEquals(1f, FloatingOverlayGeometry.easeOutCubic(1f), 0f)
        assertEquals(0.875f, FloatingOverlayGeometry.easeOutCubic(0.5f), 0.0001f)
        assertEquals(
            88,
            FloatingOverlayGeometry.interpolate(
                0,
                100,
                FloatingOverlayGeometry.easeOutCubic(0.5f),
            ),
        )
    }

    @Test
    fun crampedBoundsStillProduceAValidSinglePosition() {
        val cramped = FloatingOverlayGeometry.bounds(
            screenWidth = 60,
            screenHeight = 60,
            ballSize = 88,
            margin = 4,
            insetLeft = 5,
            insetTop = 7,
            insetRight = 5,
            insetBottom = 7,
        )

        assertEquals(cramped.minX, cramped.maxX)
        assertEquals(cramped.minY, cramped.maxY)
        assertEquals(cramped.minY, FloatingOverlayGeometry.yFromNormalized(0.9f, cramped))
    }
}
