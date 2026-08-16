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
}
