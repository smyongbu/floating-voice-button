package com.smyongbu.voiceinput

internal object RecognitionText {
    fun cleanRealtime(text: String): String = text
        .replace(Regex("<[^>]+>"), " ")
        .replace(Regex("\\s+"), " ")
        .trim()
}
