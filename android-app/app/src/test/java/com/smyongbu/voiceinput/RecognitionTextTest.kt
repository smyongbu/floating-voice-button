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
}
