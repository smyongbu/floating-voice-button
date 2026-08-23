package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

class TranscribeCppRecognizerTest {
    @Test fun finalModelWireValuesMapToThePinnedResources() {
        val whisper = TranscribeCppRecognizer.specFor(
            RecognitionController.FINAL_FASTER_WHISPER_SMALL
        )
        assertEquals("faster-whisper-small-gguf-q8-0", whisper.resourceId)
        assertEquals("whisper-small-Q8_0.gguf", whisper.fileName)

        val qwen = TranscribeCppRecognizer.specFor(
            RecognitionController.FINAL_QWEN3_ASR_17B_Q5_K_M
        )
        assertEquals("qwen3-asr-1.7b-gguf-q5-k-m", qwen.resourceId)
        assertEquals("Qwen3-ASR-1.7B-Q5_K_M.gguf", qwen.fileName)
    }

    @Test fun languageHintUsesAutodetectUnlessChineseOrEnglishIsExplicit() {
        assertEquals("", TranscribeCppRecognizer.normalizeLanguageHint(null))
        assertEquals("zh", TranscribeCppRecognizer.normalizeLanguageHint(" ZH "))
        assertEquals("en", TranscribeCppRecognizer.normalizeLanguageHint("en"))
        assertEquals("", TranscribeCppRecognizer.normalizeLanguageHint("auto"))
        assertEquals("", TranscribeCppRecognizer.normalizeLanguageHint("de"))
    }

    @Test fun transcriptCleanerKeepsMixedChineseEnglishAndPunctuation() {
        assertEquals(
            "今天测试 OpenAI voice input。",
            TranscribeCppRecognizer.cleanTranscript(
                " <|zh|>  今天测试 OpenAI\nvoice input。 "
            )
        )
    }

    @Test fun cancelAndCloseCannotUseTheNativeHandleAtTheSameTime() {
        val handle = TranscribeNativeHandle(42L)
        val cancelEntered = CountDownLatch(1)
        val allowCancelToReturn = CountDownLatch(1)
        val detached = AtomicLong(-1L)
        val detachFinished = CountDownLatch(1)

        val cancelThread = Thread {
            handle.withOpenHandle {
                assertEquals(42L, it)
                cancelEntered.countDown()
                allowCancelToReturn.await()
            }
        }
        val closeThread = Thread {
            detached.set(handle.detach())
            detachFinished.countDown()
        }

        cancelThread.start()
        try {
            assertTrue(cancelEntered.await(1, TimeUnit.SECONDS))
            closeThread.start()
            assertFalse(detachFinished.await(100, TimeUnit.MILLISECONDS))
        } finally {
            allowCancelToReturn.countDown()
        }
        assertTrue(detachFinished.await(1, TimeUnit.SECONDS))
        cancelThread.join(1_000)
        closeThread.join(1_000)

        assertFalse(cancelThread.isAlive)
        assertFalse(closeThread.isAlive)
        assertEquals(42L, detached.get())
        var lateCancelRan = false
        handle.withOpenHandle { lateCancelRan = true }
        assertFalse(lateCancelRan)
        assertEquals(0L, handle.detach())
    }

    @Test fun cancellationDuringNativeResetIsReasserted() {
        val cancellation = TranscribeCancellationGeneration()
        val resetEntered = CountDownLatch(1)
        val allowResetToReturn = CountDownLatch(1)
        val nativeCancelCalls = AtomicInteger(0)

        val prepareThread = Thread {
            cancellation.prepareForSession(
                reset = {
                    resetEntered.countDown()
                    allowResetToReturn.await()
                },
                reassertCancellation = { nativeCancelCalls.incrementAndGet() },
            )
        }

        prepareThread.start()
        try {
            assertTrue(resetEntered.await(1, TimeUnit.SECONDS))
            cancellation.markCancelled()
            nativeCancelCalls.incrementAndGet()
        } finally {
            allowResetToReturn.countDown()
        }
        prepareThread.join(1_000)

        assertFalse(prepareThread.isAlive)
        assertEquals(2, nativeCancelCalls.get())
    }

    @Test fun cancellationBeforeTheNextTranscriptionDoesNotPoisonIt() {
        val cancellation = TranscribeCancellationGeneration()
        cancellation.markCancelled()
        var resetRan = false
        var cancellationWasReasserted = false

        cancellation.prepareForSession(
            reset = { resetRan = true },
            reassertCancellation = { cancellationWasReasserted = true },
        )

        assertTrue(resetRan)
        assertFalse(cancellationWasReasserted)
    }
}
