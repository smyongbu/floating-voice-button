package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Test

class RecordingLimitTest {
    @Test fun preparationDoesNotConsumeTime() {
        assertEquals(180_000L, RecordingLimit.remainingMs(-1, 900_000))
    }

    @Test fun captureStopsAtThreeMinuteBoundary() {
        assertEquals(180_000L, RecordingLimit.remainingMs(50_000, 50_000))
        assertEquals(1L, RecordingLimit.remainingMs(50_000, 229_999))
        assertEquals(0L, RecordingLimit.remainingMs(50_000, 230_000))
        assertEquals(0L, RecordingLimit.remainingMs(50_000, 999_999))
        assertEquals(2_880_000, RecordingLimit.MAX_SAMPLES)
    }

    @Test fun newCaptureHasIndependentDeadline() {
        assertEquals(0L, RecordingLimit.remainingMs(0, 180_000))
        assertEquals(180_000L, RecordingLimit.remainingMs(180_000, 180_000))
    }
}
