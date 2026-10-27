package com.smyongbu.voiceinput

/** 收音层统一上限，网页与悬浮入口共用。时间参数采用 elapsedRealtime。 */
internal object RecordingLimit {
    const val DURATION_MS = 180_000L
    const val SAMPLE_RATE = 16_000
    const val MAX_SAMPLES = SAMPLE_RATE * 180

    fun remainingMs(startedAt: Long, now: Long): Long =
        if (startedAt < 0) DURATION_MS
        else (DURATION_MS - (now - startedAt).coerceAtLeast(0)).coerceIn(0, DURATION_MS)
}
