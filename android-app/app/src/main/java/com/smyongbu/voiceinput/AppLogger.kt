package com.smyongbu.voiceinput

import android.content.Context
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

class AppLogger(context: Context) {
    private val directory = File(context.filesDir, "logs").apply { mkdirs() }
    private val runLog = File(directory, "运行.log")
    private val errorLog = File(directory, "错误.log")
    private val formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    fun info(message: String, operationId: String = "app") =
        append(runLog, "信息", operationId, message)

    fun warning(message: String, operationId: String = "app") =
        append(errorLog, "警告", operationId, message)

    fun error(message: String, throwable: Throwable? = null, operationId: String = "app") {
        val details = throwable?.let {
            "$message（${it.javaClass.simpleName}: ${it.message.orEmpty()}）\n${it.stackTraceToString()}"
        } ?: message
        append(errorLog, "错误", operationId, details)
    }

    private fun append(file: File, level: String, operationId: String, message: String) {
        synchronized(fileLock) {
            rotate(file)
            val safeOperation = operationId.replace(Regex("[^A-Za-z0-9._-]"), "_").take(80)
            file.appendText(
                "${LocalDateTime.now().format(formatter)} [$level] [操作=$safeOperation] $message\n",
                Charsets.UTF_8
            )
        }
    }

    private fun rotate(file: File) {
        if (!file.exists() || file.length() <= MAX_BYTES) return
        val backup = File(file.parentFile, "${file.name}.1")
        if (backup.exists()) backup.delete()
        file.renameTo(backup)
    }

    companion object {
        private const val MAX_BYTES = 512 * 1024
        private val fileLock = Any()
    }
}
