package com.smyongbu.voiceinput

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

class WhisperAcftRecognizerTest {
    @Test fun dynamicAudioContextFollowsActualAudioLengthAndCapsAtThirtySeconds() {
        assertEquals(0, WhisperAcftRecognizer.calculateDynamicAudioContext(0))
        assertEquals(50, WhisperAcftRecognizer.calculateDynamicAudioContext(16_000))
        assertEquals(1_500, WhisperAcftRecognizer.calculateDynamicAudioContext(480_000))
        assertEquals(1_500, WhisperAcftRecognizer.calculateDynamicAudioContext(960_000))
    }

    @Test fun languageHintSupportsAutoChineseAndEnglishOnly() {
        assertEquals("auto", WhisperAcftRecognizer.normalizeLanguageHint(null))
        assertEquals("zh", WhisperAcftRecognizer.normalizeLanguageHint(" ZH "))
        assertEquals("en", WhisperAcftRecognizer.normalizeLanguageHint("en"))
        assertEquals("auto", WhisperAcftRecognizer.normalizeLanguageHint("de"))
    }

    @Test fun transcriptCleanerKeepsMixedChineseAndEnglish() {
        assertEquals(
            "今天测试 OpenAI voice input。",
            WhisperAcftRecognizer.cleanTranscript(" <|zh|>  今天测试 OpenAI\nvoice input。 ")
        )
    }

    @Test fun cancelAndCloseCannotUseTheNativeHandleAtTheSameTime() {
        val handle = WhisperNativeHandle(42L)
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
        val cancellation = WhisperCancellationGeneration()
        val resetEntered = CountDownLatch(1)
        val allowResetToReturn = CountDownLatch(1)
        val nativeCancelCalls = AtomicInteger(0)

        val prepareThread = Thread {
            cancellation.prepareForSession(
                reset = {
                    resetEntered.countDown()
                    allowResetToReturn.await()
                },
                reassertCancellation = { nativeCancelCalls.incrementAndGet() }
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
        val cancellation = WhisperCancellationGeneration()
        cancellation.markCancelled()
        var resetRan = false
        var cancellationWasReasserted = false

        cancellation.prepareForSession(
            reset = { resetRan = true },
            reassertCancellation = { cancellationWasReasserted = true }
        )

        assertTrue(resetRan)
        assertFalse(cancellationWasReasserted)
    }

    @Test fun cancellationAfterSessionPreparationRemainsSetUntilTranscription() {
        val cancellation = WhisperCancellationGeneration()
        var nativeCancellationFlag = true

        cancellation.prepareForSession(
            reset = { nativeCancellationFlag = false },
            reassertCancellation = { nativeCancellationFlag = true }
        )
        assertFalse(nativeCancellationFlag)

        cancellation.markCancelled()
        nativeCancellationFlag = true

        // transcribe() deliberately performs no reset, so this cancellation
        // remains visible to whisper.cpp's abort callback.
        assertTrue(nativeCancellationFlag)
    }
}
