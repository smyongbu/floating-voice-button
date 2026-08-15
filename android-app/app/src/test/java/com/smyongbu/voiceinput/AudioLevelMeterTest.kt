package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class AudioLevelMeterTest {
    @Test fun emptyInputIsSilent() {
        assertEquals(0f, AudioLevelMeter.fromPcm16(shortArrayOf(), 0))
    }

    @Test fun silenceIsSilent() {
        assertEquals(0f, AudioLevelMeter.fromPcm16(ShortArray(320), 320))
    }

    @Test fun louderInputProducesHigherLevel() {
        val quiet = AudioLevelMeter.fromPcm16(ShortArray(320) { 100 }, 320)
        val voice = AudioLevelMeter.fromPcm16(ShortArray(320) { 1500 }, 320)
        val loud = AudioLevelMeter.fromPcm16(ShortArray(320) { 9000 }, 320)
        assertTrue(quiet < voice)
        assertTrue(voice < loud)
    }

    @Test fun levelStaysWithinRangeAndSaturates() {
        val level = AudioLevelMeter.fromPcm16(ShortArray(320) { 30000 }, 320)
        assertTrue(level in 0f..1f)
        assertTrue(level > 0.9f)
    }

    @Test fun positiveAndNegativeSignalsMatch() {
        val positive = AudioLevelMeter.fromPcm16(ShortArray(320) { 4000 }, 320)
        val negative = AudioLevelMeter.fromPcm16(ShortArray(320) { -4000 }, 320)
        assertTrue(abs(positive - negative) < 0.0001f)
    }
}
