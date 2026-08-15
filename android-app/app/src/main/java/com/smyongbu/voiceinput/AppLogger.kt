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
    @Synchronized fun info(message: String) = append(runLog, "信息", message)
    @Synchronized fun error(message: String, throwable: Throwable? = null) = append(errorLog, "错误", "$message${throwable?.let { "（${it.javaClass.simpleName}）" } ?: ""}")
    private fun append(file: File, level: String, message: String) { rotate(file); file.appendText("${LocalDateTime.now().format(formatter)} [$level] $message\n", Charsets.UTF_8) }
    private fun rotate(file: File) { if (file.exists() && file.length() > 512 * 1024) { val backup = File(file.parentFile, "${file.name}.1"); if (backup.exists()) backup.delete(); file.renameTo(backup) } }
}
