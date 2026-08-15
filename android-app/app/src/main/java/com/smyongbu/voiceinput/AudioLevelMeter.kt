package com.smyongbu.voiceinput

import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sqrt

object AudioLevelMeter {
    fun fromPcm16(samples: ShortArray, count: Int): Float {
        if (count <= 0) return 0f
        var sum = 0.0
        var used = 0
        for (i in 0 until count step 2) { val value = samples[i] / 32768.0; sum += value * value; used++ }
        val rms = sqrt(sum / max(used, 1)); val db = 20.0 * log10(max(rms, 1e-6))
        return (((db + 58.0) / 46.0).coerceIn(0.0, 1.0).pow(0.65)).toFloat()
    }
}
