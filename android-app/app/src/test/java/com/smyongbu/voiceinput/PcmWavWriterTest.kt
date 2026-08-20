package com.smyongbu.voiceinput

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class PcmWavWriterTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun writesMonoPcm16WaveWithExpectedHeaderAndSamples() {
        val output = File(temporaryFolder.newFolder("wav"), "recording.wav")
        val samples = FloatArray(160).apply {
            this[0] = -1f
            this[1] = 0f
            this[2] = 1f
            this[3] = Float.NaN
        }

        val info = PcmWavWriter.writeMono16(output, samples, 16_000)
        val bytes = output.readBytes()

        assertArrayEquals("RIFF".toByteArray(), bytes.copyOfRange(0, 4))
        assertEquals(36L + 320L, uint32Le(bytes, 4))
        assertArrayEquals("WAVE".toByteArray(), bytes.copyOfRange(8, 12))
        assertArrayEquals("fmt ".toByteArray(), bytes.copyOfRange(12, 16))
        assertEquals(16L, uint32Le(bytes, 16))
        assertEquals(1, uint16Le(bytes, 20))
        assertEquals(1, uint16Le(bytes, 22))
        assertEquals(16_000L, uint32Le(bytes, 24))
        assertEquals(32_000L, uint32Le(bytes, 28))
        assertEquals(2, uint16Le(bytes, 32))
        assertEquals(16, uint16Le(bytes, 34))
        assertArrayEquals("data".toByteArray(), bytes.copyOfRange(36, 40))
        assertEquals(320L, uint32Le(bytes, 40))
        assertArrayEquals(
            byteArrayOf(0x00, 0x80.toByte(), 0x00, 0x00, 0xff.toByte(), 0x7f, 0x00, 0x00),
            bytes.copyOfRange(44, 52),
        )
        assertEquals(10L, info.durationMs)
        assertEquals(364L, info.audioBytes)
        assertEquals(info.audioBytes, output.length())
    }

    @Test
    fun rejectsUnsupportedSampleRateWithoutCreatingFile() {
        val output = File(temporaryFolder.newFolder("invalid"), "recording.wav")

        assertThrows(IllegalArgumentException::class.java) {
            PcmWavWriter.writeMono16(output, floatArrayOf(0f), 1_000)
        }

        assertFalse(output.exists())
    }

    private fun uint16Le(bytes: ByteArray, offset: Int): Int =
        (bytes[offset].toInt() and 0xff) or
            ((bytes[offset + 1].toInt() and 0xff) shl 8)

    private fun uint32Le(bytes: ByteArray, offset: Int): Long =
        (bytes[offset].toLong() and 0xff) or
            ((bytes[offset + 1].toLong() and 0xff) shl 8) or
            ((bytes[offset + 2].toLong() and 0xff) shl 16) or
            ((bytes[offset + 3].toLong() and 0xff) shl 24)
}
