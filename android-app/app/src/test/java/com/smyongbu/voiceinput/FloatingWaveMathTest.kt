package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FloatingWaveMathTest {
    @Test
    fun audioLevelRaisesAmplitudeAndSpeedWithinExpectedRange() {
        val silentAmplitude = FloatingWaveMath.targetAmplitude(0f)
        val loudAmplitude = FloatingWaveMath.targetAmplitude(1f)
        val silentSpeed = FloatingWaveMath.targetSpeed(0f)
        val loudSpeed = FloatingWaveMath.targetSpeed(1f)

        assertEquals(0.1f, silentAmplitude, 0.0001f)
        assertEquals(0.88f, loudAmplitude, 0.0001f)
        assertTrue(loudAmplitude > silentAmplitude)
        assertTrue(loudSpeed > silentSpeed)
    }

    @Test
    fun waveEnvelopeClosesAtBothEdges() {
        assertEquals(0f, FloatingWaveMath.sample(0f, 2.25f, 0.7f), 0.0001f)
        assertEquals(0f, FloatingWaveMath.sample(1f, 2.25f, 0.7f), 0.0001f)
    }

    @Test
    fun smoothingMovesTowardTargetWithoutOvershoot() {
        val rising = FloatingWaveMath.smooth(0.08f, 0.88f, 0.016f, 0.045f)
        val falling = FloatingWaveMath.smooth(0.88f, 0.08f, 0.016f, 0.22f)

        assertTrue(rising in 0.08f..0.88f)
        assertTrue(falling in 0.08f..0.88f)
        assertTrue(rising > 0.08f)
        assertTrue(falling < 0.88f)
    }

    @Test
    fun shapeMorphKeepsExactEndpoints() {
        assertEquals(0f, FloatingWaveMath.smoothStep(0f), 0.0001f)
        assertEquals(1f, FloatingWaveMath.smoothStep(1f), 0.0001f)
        assertTrue(FloatingWaveMath.smoothStep(0.5f) in 0f..1f)
    }
}
