package com.smyongbu.voiceinput

internal enum class RecognitionResultSource { NONE, REALTIME, CORRECTED }

internal data class FinalRecognition(
    val text: String,
    val source: RecognitionResultSource
)

internal object RecognitionText {
    fun cleanRealtime(text: String): String = text
        .replace(Regex("<[^>]+>"), " ")
        .replace(Regex("\\s+"), " ")
        .trim()

    fun formatRealtime(text: String): String = cleanRealtime(text).replace(
        Regex("[A-Za-z]+(?:[-'][A-Za-z]+)*")
    ) { word ->
        word.value.replace(Regex("[A-Za-z]+")) { part ->
            part.value.first().uppercase() + part.value.drop(1).lowercase()
        }
    }

    fun combineSegments(existing: String, incoming: String): String {
        val left = cleanRealtime(existing)
        val right = cleanRealtime(incoming)
        if (left.isEmpty()) return right
        if (right.isEmpty()) return left

        val last = left.last()
        val first = right.first()
        val needsSpace = last.isLetterOrDigit() && first.isLetterOrDigit() &&
            (last.code < 128 || first.code < 128)
        return left + (if (needsSpace) " " else "") + right
    }

    fun chooseFinal(realtime: String, corrected: String): FinalRecognition {
        val live = cleanRealtime(realtime)
        val final = cleanRealtime(corrected)
        if (live.isEmpty() && final.isEmpty()) return FinalRecognition("", RecognitionResultSource.NONE)
        if (final.isEmpty()) return FinalRecognition(live, RecognitionResultSource.REALTIME)
        if (live.isEmpty()) return FinalRecognition(final, RecognitionResultSource.CORRECTED)

        val liveLength = meaningfulLength(live)
        val finalLength = meaningfulLength(final)
        if (finalLength * 10 < liveLength * 7) {
            return FinalRecognition(live, RecognitionResultSource.REALTIME)
        }
        if (finalLength > liveLength * 2 + 8) {
            return FinalRecognition(live, RecognitionResultSource.REALTIME)
        }

        if (textualSimilarity(live, final) < 0.42) {
            return FinalRecognition(live, RecognitionResultSource.REALTIME)
        }

        if (isEnglishHeavy(live)) {
            val liveFragments = fragmentedEnglishScore(live)
            val finalFragments = fragmentedEnglishScore(final)
            if (finalFragments > liveFragments + 1 || finalLength * 20 < liveLength * 17) {
                return FinalRecognition(live, RecognitionResultSource.REALTIME)
            }
        }
        return FinalRecognition(final, RecognitionResultSource.CORRECTED)
    }

    private fun meaningfulLength(text: String): Int = text.count { it.isLetterOrDigit() }

    private fun isEnglishHeavy(text: String): Boolean {
        val latin = text.count { it.code < 128 && it.isLetter() }
        val han = text.count { Character.UnicodeScript.of(it.code) == Character.UnicodeScript.HAN }
        return latin >= 6 && latin > han * 2
    }

    private fun fragmentedEnglishScore(text: String): Int = text
        .lowercase()
        .split(Regex("\\s+"))
        .count { it.length == 1 && it[0] in 'b'..'z' && it != "i" }

    private fun textualSimilarity(left: String, right: String): Double {
        val first = left.lowercase().filter { it.isLetterOrDigit() }
        val second = right.lowercase().filter { it.isLetterOrDigit() }
        if (first == second) return 1.0
        if (first.length < 2 || second.length < 2) return 0.0
        val firstPairs = first.windowed(2).toSet()
        val secondPairs = second.windowed(2).toSet()
        val shared = firstPairs.count(secondPairs::contains)
        return shared * 2.0 / (firstPairs.size + secondPairs.size)
    }
}
