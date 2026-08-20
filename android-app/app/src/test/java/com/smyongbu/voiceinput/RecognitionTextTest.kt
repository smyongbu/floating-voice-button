package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Test

class RecognitionTextTest {
    @Test fun removesInternalTokensFromRealtimeText() {
        assertEquals("hello 世界", RecognitionText.cleanRealtime("<nuk> hello <blank> 世界"))
    }

    @Test fun internalTokenOnlyBecomesEmpty() {
        assertEquals("", RecognitionText.cleanRealtime(" <nuk> "))
    }

    @Test fun realtimeEnglishUsesTitleCaseWithoutChangingFinalCleaner() {
        assertEquals(
            "Hello World 和 Open-Ai",
            RecognitionText.formatRealtime("<nuk> HELLO WORLD 和 OPEN-AI")
        )
        assertEquals("PLEASE KEEP API", RecognitionText.cleanRealtime("PLEASE KEEP API"))
    }

    @Test fun preservesWordsRepeatedAcrossEndpointSegments() {
        assertEquals(
            "VERY VERY GOOD",
            RecognitionText.combineSegments("VERY", "VERY GOOD")
        )
        assertEquals("好好我们继续", RecognitionText.combineSegments("好", "好我们继续"))
    }

    @Test fun combinesChineseAndEnglishWithReadableSpacing() {
        assertEquals("请打开 Wi-Fi", RecognitionText.combineSegments("请打开", "Wi-Fi"))
        assertEquals("OpenAI 明天下午", RecognitionText.combineSegments("OpenAI", "明天下午"))
    }

    @Test fun keepsLongerRealtimeResultWhenCorrectionDropsMostOfSentence() {
        val result = RecognitionText.chooseFinal(
            "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG",
            "THE QUICK FOX"
        )
        assertEquals(RecognitionResultSource.REALTIME, result.source)
        assertEquals("THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG", result.text)
    }

    @Test fun keepsRealtimeWhenEnglishCorrectionIsFragmented() {
        val result = RecognitionText.chooseFinal(
            "OPEN AI GPT FIVE WILL START NOW",
            "OPEN A I G P T FIVE WILL START NOW"
        )
        assertEquals(RecognitionResultSource.REALTIME, result.source)
    }

    @Test fun keepsRealtimeWhenSimilarLengthCorrectionHasDifferentContent() {
        val result = RecognitionText.chooseFinal(
            "PLEASE OPEN WIFI AND SEARCH OPEN AI",
            "明天下午记得带雨伞去公园散步"
        )
        assertEquals(RecognitionResultSource.REALTIME, result.source)
    }

    @Test fun usesRelatedCorrectionWhenMeaningfulContentIsPreserved() {
        val result = RecognitionText.chooseFinal(
            "PLEASE OPEN WIFI AND SEARCH OPEN AI",
            "PLEASE OPEN WI-FI AND SEARCH OPENAI"
        )
        assertEquals(RecognitionResultSource.CORRECTED, result.source)
    }

    @Test fun rejectsUnrelatedLongCorrectionEvenWhenItContainsTheRealtimeTail() {
        val result = RecognitionText.chooseFinal(
            "今天我们测试实时与 coqteon test",
            "人依依旧他上上线类似于你妈小时候会给定的婴儿杂志上投到你的照今天我们测试实时与 coqteon test"
        )
        assertEquals(RecognitionResultSource.REALTIME, result.source)
    }

    @Test fun usesRelatedCorrectionWhenItAddsModerateMixedLanguageContent() {
        val result = RecognitionText.chooseFinal(
            "请打开 Wi-Fi and search OpenAI",
            "请打开 Wi-Fi and search OpenAI GPT five"
        )
        assertEquals(RecognitionResultSource.CORRECTED, result.source)
    }

    @Test fun whisperWinsEvenWhenItCorrectsACompletelyDifferentDraft() {
        val result = RecognitionText.chooseWhisperFinal(
            realtime = "今天下午开一个破见会议",
            whisper = "今天下午开 project meeting，please bring the sales report。",
            audioSampleCount = 16000 * 5,
        )
        assertEquals(RecognitionResultSource.CORRECTED, result.source)
        assertEquals("今天下午开 project meeting，please bring the sales report。", result.text)
    }

    @Test fun whisperDoesNotUseRelativeLengthAsARejectionRule() {
        val shorter = RecognitionText.chooseWhisperFinal(
            realtime = "这是一个很长但是有很多错误而且重复的实时初稿",
            whisper = "正确短句",
            audioSampleCount = 16000 * 3,
        )
        val longer = RecognitionText.chooseWhisperFinal(
            realtime = "开会",
            whisper = "今天下午三点开 project meeting 并把完整报告发给 Alice",
            audioSampleCount = 16000 * 4,
        )
        assertEquals(RecognitionResultSource.CORRECTED, shorter.source)
        assertEquals(RecognitionResultSource.CORRECTED, longer.source)
    }

    @Test fun invalidWhisperOutputFallsBackToRealtime() {
        listOf("", "……？！", "有效前缀\u0000异常").forEach { invalid ->
            val result = RecognitionText.chooseWhisperFinal(
                realtime = "保留实时初稿",
                whisper = invalid,
                audioSampleCount = 16000 * 2,
            )
            assertEquals(RecognitionResultSource.REALTIME, result.source)
            assertEquals("保留实时初稿", result.text)
        }
    }

    @Test fun impossibleWhisperOutputRateFallsBackToRealtime() {
        val result = RecognitionText.chooseWhisperFinal(
            realtime = "保留实时初稿",
            whisper = "字".repeat(200),
            audioSampleCount = 16000,
        )
        assertEquals(RecognitionResultSource.REALTIME, result.source)
    }

    @Test fun mechanicalWhisperLoopFallsBackButNormalRepeatDoesNot() {
        val loop = RecognitionText.chooseWhisperFinal(
            realtime = "保留实时初稿",
            whisper = "感谢观看".repeat(12),
            audioSampleCount = 16000 * 8,
        )
        val normal = RecognitionText.chooseWhisperFinal(
            realtime = "",
            whisper = "这个这个问题需要再确认一次",
            audioSampleCount = 16000 * 3,
        )
        val shortEmphasis = RecognitionText.chooseWhisperFinal(
            realtime = "",
            whisper = "哈哈哈哈哈哈哈哈",
            audioSampleCount = 16000 * 2,
        )
        assertEquals(RecognitionResultSource.REALTIME, loop.source)
        assertEquals(RecognitionResultSource.CORRECTED, normal.source)
        assertEquals(RecognitionResultSource.CORRECTED, shortEmphasis.source)
    }

    @Test fun standaloneWhisperCanProduceOrRejectTheOnlyResult() {
        val valid = RecognitionText.chooseWhisperFinal(
            realtime = "",
            whisper = "你好 Hello",
            audioSampleCount = 16000 * 2,
        )
        val empty = RecognitionText.chooseWhisperFinal(
            realtime = "",
            whisper = "！",
            audioSampleCount = 16000 * 2,
        )
        assertEquals(RecognitionResultSource.CORRECTED, valid.source)
        assertEquals(RecognitionResultSource.NONE, empty.source)
    }

    @Test fun whisperOutputAtFortyCharactersPerSecondIsAccepted() {
        val eightyDistinctCharacters = (0 until 80).joinToString("") {
            (0x4E00 + it).toChar().toString()
        }
        val result = RecognitionText.chooseWhisperFinal(
            realtime = "",
            whisper = eightyDistinctCharacters,
            audioSampleCount = 16000 * 2,
        )
        assertEquals(RecognitionResultSource.CORRECTED, result.source)
    }
}
