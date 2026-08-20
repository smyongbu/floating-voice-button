package com.smyongbu.voiceinput

import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import kotlin.math.roundToInt

data class PcmWavInfo(
    val durationMs: Long,
    val audioBytes: Long,
)

object PcmWavWriter {
    fun writeMono16(file: File, samples: FloatArray, sampleRateHz: Int): PcmWavInfo {
        require(sampleRateHz in MIN_SAMPLE_RATE_HZ..MAX_SAMPLE_RATE_HZ) {
            "不支持的采样率：$sampleRateHz"
        }
        val dataBytes = samples.size.toLong() * BYTES_PER_SAMPLE
        require(dataBytes + RIFF_HEADER_BYTES <= UINT32_MAX) { "录音过长，无法写入 WAV" }

        file.parentFile?.let { parent ->
            if (!parent.exists() && !parent.mkdirs()) {
                throw IllegalStateException("无法创建 WAV 输出目录")
            }
            check(parent.isDirectory) { "WAV 输出目录不可用" }
        }
        check(!file.exists()) { "WAV 输出文件已经存在" }

        try {
            FileOutputStream(file, false).use { fileOutput ->
                BufferedOutputStream(fileOutput, OUTPUT_BUFFER_BYTES).use { output ->
                    writeAscii(output, "RIFF")
                    writeUInt32Le(output, 36L + dataBytes)
                    writeAscii(output, "WAVE")
                    writeAscii(output, "fmt ")
                    writeUInt32Le(output, 16L)
                    writeUInt16Le(output, PCM_FORMAT)
                    writeUInt16Le(output, CHANNEL_COUNT)
                    writeUInt32Le(output, sampleRateHz.toLong())
                    writeUInt32Le(output, sampleRateHz.toLong() * BYTES_PER_SAMPLE)
                    writeUInt16Le(output, BYTES_PER_SAMPLE)
                    writeUInt16Le(output, BITS_PER_SAMPLE)
                    writeAscii(output, "data")
                    writeUInt32Le(output, dataBytes)
                    samples.forEach { sample -> writePcm16Le(output, sample) }
                    output.flush()
                    fileOutput.fd.sync()
                }
            }
        } catch (error: Throwable) {
            runCatching { file.delete() }
            throw error
        }

        return PcmWavInfo(
            durationMs = samples.size.toLong() * 1_000L / sampleRateHz,
            audioBytes = file.length(),
        )
    }

    private fun writePcm16Le(output: OutputStream, rawSample: Float) {
        val sample = if (rawSample.isFinite()) rawSample.coerceIn(-1f, 1f) else 0f
        val pcm = when {
            sample <= -1f -> Short.MIN_VALUE.toInt()
            sample >= 1f -> Short.MAX_VALUE.toInt()
            sample < 0f -> (sample * 32_768f).roundToInt()
            else -> (sample * 32_767f).roundToInt()
        }
        writeUInt16Le(output, pcm and 0xffff)
    }

    private fun writeAscii(output: OutputStream, value: String) {
        value.forEach { output.write(it.code) }
    }

    private fun writeUInt16Le(output: OutputStream, value: Int) {
        require(value in 0..0xffff)
        output.write(value and 0xff)
        output.write((value ushr 8) and 0xff)
    }

    private fun writeUInt32Le(output: OutputStream, value: Long) {
        require(value in 0L..UINT32_MAX)
        output.write((value and 0xff).toInt())
        output.write(((value ushr 8) and 0xff).toInt())
        output.write(((value ushr 16) and 0xff).toInt())
        output.write(((value ushr 24) and 0xff).toInt())
    }

    private const val MIN_SAMPLE_RATE_HZ = 8_000
    private const val MAX_SAMPLE_RATE_HZ = 384_000
    private const val CHANNEL_COUNT = 1
    private const val PCM_FORMAT = 1
    private const val BITS_PER_SAMPLE = 16
    private const val BYTES_PER_SAMPLE = 2
    private const val RIFF_HEADER_BYTES = 44L
    private const val UINT32_MAX = 0xffff_ffffL
    private const val OUTPUT_BUFFER_BYTES = 64 * 1024
}
