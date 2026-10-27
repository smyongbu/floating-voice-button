package com.smyongbu.voiceinput

import java.io.File
import java.io.IOException
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

internal object BundledModelFile {
    fun install(
        target: File,
        bytes: Long,
        expectedHash: String,
        open: () -> InputStream,
        progress: (Long) -> Unit = {},
    ) {
        if (target.isFile && target.length() == bytes && hash(target) == expectedHash) return
        target.parentFile?.mkdirs()
        val part = File(target.parentFile, target.name + ".part")
        val digest = MessageDigest.getInstance("SHA-256")
        var written = 0L
        open().buffered().use { input ->
            part.outputStream().buffered().use { output ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (count == 0) continue
                    written += count
                    if (written > bytes) throw IOException("内置模型大小超过清单")
                    output.write(buffer, 0, count)
                    digest.update(buffer, 0, count)
                    progress(written)
                }
            }
        }
        val actualHash = digest.digest().joinToString("") { "%02x".format(it) }
        if (written != bytes || actualHash != expectedHash) throw IOException("内置模型完整性校验失败")
        try {
            Files.move(part.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(part.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
    }

    private fun hash(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
