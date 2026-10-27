package com.smyongbu.voiceinput

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

data class ModelResourceState(
    val id: String,
    val name: String,
    val purpose: String,
    val version: String,
    val totalBytes: Long,
    val presentBytes: Long,
    val installedBytes: Long,
    val status: String,
    val speedBytesPerSecond: Long,
    val etaSeconds: Long,
    val freeBytes: Long,
    val errorMessage: String
)

object ModelResourceManager {
    const val STREAMING_PARAFORMER_ID = "streaming-paraformer-bilingual-zh-en"
    const val FASTER_WHISPER_SMALL_ID = "faster-whisper-small-gguf-q8-0"
    const val FASTER_WHISPER_SMALL_FILE = "whisper-small-Q8_0.gguf"
    const val QWEN_17B_ID = "qwen3-asr-1.7b-gguf-q5-k-m"
    const val QWEN_17B_FILE = "Qwen3-ASR-1.7B-Q5_K_M.gguf"
    val RECOGNITION_RESOURCE_IDS = setOf(
        STREAMING_PARAFORMER_ID,
        FASTER_WHISPER_SMALL_ID,
        QWEN_17B_ID,
    )

    interface Listener {
        fun onModelResourcesChanged(states: List<ModelResourceState>)
    }

    private data class FileSpec(
        val relativePath: String,
        val url: String,
        val bytes: Long,
        val sha256: String
    )

    private data class BundleSpec(
        val id: String,
        val name: String,
        val purpose: String,
        val version: String,
        val files: List<FileSpec>
    ) {
        val totalBytes: Long = files.sumOf { it.bytes }
    }

    private data class RuntimeState(
        val status: String,
        val speed: Long = 0,
        val eta: Long = 0,
        val error: String = ""
    )

    private data class DownloadTask(
        val paused: AtomicBoolean = AtomicBoolean(false),
        val cancelled: AtomicBoolean = AtomicBoolean(false)
    )

    private class DownloadPaused : Exception()
    private class DownloadCancelled : Exception()

    private val fallbackBundles = listOf(
        BundleSpec(
            id = STREAMING_PARAFORMER_ID,
            name = "Streaming Paraformer",
            purpose = "边说边显示中英文识别文字",
            version = "8e40c43232a1c5c66c82111efc5820d3accca11b-int8",
            files = listOf(
                FileSpec(
                    "encoder.int8.onnx",
                    "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/8e40c43232a1c5c66c82111efc5820d3accca11b/encoder.int8.onnx",
                    165_462_184,
                    "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a",
                ),
                FileSpec(
                    "decoder.int8.onnx",
                    "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/8e40c43232a1c5c66c82111efc5820d3accca11b/decoder.int8.onnx",
                    71_664_561,
                    "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f",
                ),
                FileSpec(
                    "tokens.txt",
                    "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/8e40c43232a1c5c66c82111efc5820d3accca11b/tokens.txt",
                    75_756,
                    "59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6",
                ),
            ),
        ),
        BundleSpec(
            id = FASTER_WHISPER_SMALL_ID,
            name = "Faster-Whisper Small",
            purpose = "停止后生成完整的最终识别文字",
            version = "c0214bd34be9296695486f838e0142f900803159-q8_0",
            files = listOf(
                FileSpec(
                    FASTER_WHISPER_SMALL_FILE,
                    "https://huggingface.co/handy-computer/whisper-small-gguf/resolve/c0214bd34be9296695486f838e0142f900803159/whisper-small-Q8_0.gguf",
                    269_751_136,
                    "9b9c8811bbcc82a7766f0fb0925614bdacb0923b2cc630daeac17108b655b860",
                ),
            ),
        ),
        BundleSpec(
            id = QWEN_17B_ID,
            name = "Qwen3-ASR 1.7B Q5_K_M",
            purpose = "停止后生成高质量的中英文最终识别文字",
            version = "92282af1610a2db19d66f2bef1e260f5deca782d-q5_k_m",
            files = listOf(
                FileSpec(
                    QWEN_17B_FILE,
                    "https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/resolve/92282af1610a2db19d66f2bef1e260f5deca782d/Qwen3-ASR-1.7B-Q5_K_M.gguf",
                    1_517_290_464,
                    "034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0",
                ),
            ),
        ),
    )

    private val listeners = CopyOnWriteArrayList<Listener>()
    private val runtimeStates = ConcurrentHashMap<String, RuntimeState>()
    private val tasks = ConcurrentHashMap<String, DownloadTask>()
    private val taskExecutor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private lateinit var app: Context
    private lateinit var logger: AppLogger
    private lateinit var bundles: List<BundleSpec>
    private val bundledInstallActive = AtomicBoolean(false)
    private var bundledIds = emptySet<String>()

    fun init(context: Context) {
        if (::app.isInitialized) return
        synchronized(this) {
            if (::app.isInitialized) return
            app = context.applicationContext
            logger = AppLogger(app)
            bundles = runCatching { readCatalog() }.getOrElse { error ->
                logger.error("读取模型资源清单失败，使用内置保底清单", error, "model-catalog")
                fallbackBundles
            }
            rootDirectory().mkdirs()
            // 已停用模型只清理本应用私有副本，不触及其他资源。
            val retired = safeFile(rootDirectory(), "qwen3-asr-0.6b-int8")
            if (retired.exists()) {
                runCatching { check(retired.deleteRecursively()) { "旧模型清理失败" } }
                    .onSuccess { logger.info("已清理停用的 0.6B 模型", "model-cleanup") }
                    .onFailure { logger.error("停用模型清理失败，下次启动重试", it, "model-cleanup") }
            }
            bundles.filter(::isInstalled).forEach(::cleanupOldVersions)
            if (BuildConfig.BUNDLED_MODELS) {
                val metadata = app.assets.open("bundled-models.json").bufferedReader().use { JSONObject(it.readText()) }
                check(metadata.getString("variant") == "three-models") { "内置模型变体错误" }
                val resources = metadata.getJSONArray("resources")
                bundledIds = (0 until resources.length()).map { index ->
                    val resource = resources.getJSONObject(index)
                    val id = resource.getString("id")
                    val spec = bundle(id) ?: error("内置资源不在正式清单中")
                    check(resource.getString("version") == spec.version) { "内置资源版本不一致" }
                    id
                }.toSet()
                check(bundledIds == RECOGNITION_RESOURCE_IDS) { "内置模型清单不完整" }
                installBundledModels()
            }
        }
    }

    fun addListener(listener: Listener) {
        listeners += listener
        listener.onModelResourcesChanged(states())
    }

    fun removeListener(listener: Listener) {
        listeners -= listener
    }

    fun states(): List<ModelResourceState> = bundles.map(::buildState)

    fun isInstalled(id: String): Boolean = bundle(id)?.let(::isInstalled) == true

    fun bundleDirectory(id: String): File {
        ensureInitialized()
        val spec = bundle(id) ?: error("未知模型资源：$id")
        return versionDirectory(spec)
    }

    fun modelPath(id: String, relativePath: String): String {
        val spec = bundle(id) ?: error("未知模型资源：$id")
        check(isInstalled(spec)) { "模型资源尚未安装：${spec.name}" }
        return safeFile(bundleDirectory(id), relativePath).absolutePath
    }

    fun startOrResume(id: String) {
        val spec = bundle(id) ?: return
        if (isInstalled(spec)) {
            notifyChanged()
            return
        }
        if (id in bundledIds) {
            installBundledModels()
            return
        }
        tasks[id]?.let {
            it.paused.set(false)
            runtimeStates[id] = RuntimeState("downloading")
            notifyChanged()
            return
        }

        val task = DownloadTask()
        if (tasks.putIfAbsent(id, task) != null) return
        runtimeStates[id] = RuntimeState("downloading")
        notifyChanged()
        taskExecutor.execute { downloadBundle(spec, task) }
    }

    fun pause(id: String) {
        tasks[id]?.paused?.set(true)
        runtimeStates[id] = RuntimeState("pausing")
        notifyChanged()
    }

    fun verify(id: String) {
        val spec = bundle(id) ?: return
        if (!isInstalled(spec)) {
            runtimeStates[id] = RuntimeState("error", error = "模型尚未完整安装，请重新下载。")
            notifyChanged()
            return
        }
        val task = DownloadTask()
        if (tasks.putIfAbsent(id, task) != null) return
        runtimeStates[id] = RuntimeState("verifying")
        notifyChanged()
        taskExecutor.execute {
            val operationId = "model-verify-${spec.id}-${System.currentTimeMillis().toString(36)}"
            try {
                spec.files.forEach { file ->
                    val target = safeFile(versionDirectory(spec), file.relativePath)
                    if (target.length() != file.bytes || sha256(target) != file.sha256) {
                        throw IOException("SHA-256 校验失败：${file.relativePath}")
                    }
                }
                runtimeStates.remove(id)
                logger.info("模型资源完整性校验通过，资源=${spec.id}", operationId)
            } catch (error: Exception) {
                File(bundleRoot(spec), ".installed-version").delete()
                runtimeStates[id] = RuntimeState("error", error = "完整性校验失败，请重新下载。")
                logger.error("模型资源完整性校验失败，资源=${spec.id}", error, operationId)
            } finally {
                tasks.remove(id, task)
                notifyChanged()
            }
        }
    }

    fun delete(id: String): Boolean {
        val spec = bundle(id) ?: return false
        if (tasks[id] != null) return false
        val target = bundleRoot(spec).canonicalFile
        val root = rootDirectory().canonicalFile
        if (target.parentFile != root) return false
        val operationId = "model-delete-${System.currentTimeMillis().toString(36)}"
        return try {
            if (target.exists() && !target.deleteRecursively()) {
                throw IOException("模型资源目录未能完全删除")
            }
            runtimeStates.remove(id)
            logger.info("已删除模型资源，资源=${spec.id}", operationId)
            notifyChanged()
            true
        } catch (error: Exception) {
            logger.error("删除模型资源失败，资源=${spec.id}", error, operationId)
            runtimeStates[id] = RuntimeState("error", error = "删除失败，请稍后重试。")
            notifyChanged()
            false
        }
    }

    fun refresh() = notifyChanged()

    private fun installBundledModels() {
        if (!bundledInstallActive.compareAndSet(false, true)) return
        taskExecutor.execute {
            try {
                bundles.filter { it.id in bundledIds && !isInstalled(it) }.forEach { spec ->
                    val operation = "bundled-${spec.id}"
                    try {
                        runtimeStates[spec.id] = RuntimeState("installing")
                        notifyChanged()
                        logger.info("开始安装内置模型，资源=${spec.id}", operation)
                        var lastUpdate = 0L
                        spec.files.forEach { file ->
                            val target = safeFile(versionDirectory(spec), file.relativePath)
                            if (!target.exists() && rootDirectory().usableSpace < file.bytes + MINIMUM_FREE_BYTES) {
                                throw IOException("存储空间不足，无法安装内置模型")
                            }
                            BundledModelFile.install(target, file.bytes, file.sha256, {
                                app.assets.open("bundled-models/${spec.id}/${spec.version}/${file.relativePath}")
                            }) { written ->
                                val now = SystemClock.elapsedRealtime()
                                if (now - lastUpdate >= 250 || written == file.bytes) {
                                    lastUpdate = now
                                    notifyChanged()
                                }
                            }
                        }
                        writeMarker(spec)
                        cleanupOldVersions(spec)
                        runtimeStates.remove(spec.id)
                        logger.info("内置模型校验并安装完成，资源=${spec.id}", operation)
                    } catch (error: Exception) {
                        runtimeStates[spec.id] = RuntimeState("error", error = "内置模型安装失败，请释放空间后重试。")
                        logger.error("内置模型安装失败，资源=${spec.id}", error, operation)
                    }
                    notifyChanged()
                }
            } finally {
                bundledInstallActive.set(false)
            }
        }
    }

    private fun downloadBundle(spec: BundleSpec, task: DownloadTask) {
        val operationId = "model-${spec.id}-${System.currentTimeMillis().toString(36)}"
        val started = System.currentTimeMillis()
        logger.info("开始下载模型资源，资源=${spec.id}，字节=${spec.totalBytes}", operationId)
        try {
            bundleDirectory(spec.id).mkdirs()
            val requiredBytes = remainingDownloadBytes(spec)
            val freeBytes = rootDirectory().usableSpace
            if (freeBytes < requiredBytes + MINIMUM_FREE_BYTES) {
                throw IOException("space insufficient: required=$requiredBytes, free=$freeBytes")
            }
            spec.files.forEach { file ->
                checkTask(task)
                downloadFile(spec, file, task, operationId)
            }
            runtimeStates[spec.id] = RuntimeState("verifying")
            notifyChanged()
            spec.files.forEach { file ->
                val target = safeFile(bundleDirectory(spec.id), file.relativePath)
                if (target.length() != file.bytes || sha256(target) != file.sha256) {
                    throw IOException("资源完整性校验失败：${file.relativePath}")
                }
            }
            writeMarker(spec)
            cleanupOldVersions(spec)
            runtimeStates.remove(spec.id)
            logger.info(
                "模型资源下载完成，资源=${spec.id}，耗时=${System.currentTimeMillis() - started}毫秒",
                operationId
            )
        } catch (_: DownloadPaused) {
            runtimeStates[spec.id] = RuntimeState("paused")
            logger.info("模型资源下载已暂停，资源=${spec.id}", operationId)
        } catch (_: DownloadCancelled) {
            runtimeStates.remove(spec.id)
            logger.info("模型资源下载已取消，资源=${spec.id}", operationId)
        } catch (error: Exception) {
            val message = if (error.message.orEmpty().contains("space", ignoreCase = true) ||
                error.message.orEmpty().contains("ENOSPC", ignoreCase = true)
            ) {
                "存储空间不足，请清理空间后重试。"
            } else {
                "下载失败，请检查网络后重试。"
            }
            runtimeStates[spec.id] = RuntimeState("error", error = message)
            logger.error("模型资源下载失败，资源=${spec.id}", error, operationId)
        } finally {
            val resumeRequested = !task.paused.get() &&
                runtimeStates[spec.id]?.status == "downloading"
            tasks.remove(spec.id, task)
            if (resumeRequested) startOrResume(spec.id) else notifyChanged()
        }
    }

    private fun downloadFile(
        bundle: BundleSpec,
        spec: FileSpec,
        task: DownloadTask,
        operationId: String
    ) {
        val directory = bundleDirectory(bundle.id)
        val target = safeFile(directory, spec.relativePath)
        target.parentFile?.mkdirs()
        if (target.length() == spec.bytes && sha256(target) == spec.sha256) return
        if (target.exists() && !target.delete()) throw IOException("无法清理无效的模型文件")

        val part = File(target.parentFile, "${target.name}.part")
        if (part.length() > spec.bytes) part.delete()
        if (part.length() == spec.bytes) {
            if (sha256(part) == spec.sha256) {
                promotePart(part, target)
                logger.info("已复用下载完成的模型临时文件，资源=${bundle.id}，文件=${spec.relativePath}", operationId)
                return
            }
            part.delete()
        }
        var existing = part.length()
        var connection: HttpURLConnection? = null
        try {
            connection = (URL(spec.url).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = 15_000
                readTimeout = 20_000
                setRequestProperty("User-Agent", "AndroidVoiceInput/0.8")
                setRequestProperty("Accept-Encoding", "identity")
                if (existing > 0) setRequestProperty("Range", "bytes=$existing-")
            }
            val code = connection.responseCode
            if (code == 416 && existing > 0) {
                part.delete()
                connection.disconnect()
                connection = null
                downloadFile(bundle, spec, task, operationId)
                return
            }
            val append = existing > 0 && code == HttpURLConnection.HTTP_PARTIAL
            if (code !in listOf(HttpURLConnection.HTTP_OK, HttpURLConnection.HTTP_PARTIAL)) {
                throw IOException("下载服务返回状态码 $code")
            }
            if (append) {
                val match = CONTENT_RANGE.matchEntire(connection.getHeaderField("Content-Range").orEmpty())
                val start = match?.groupValues?.getOrNull(1)?.toLongOrNull()
                val total = match?.groupValues?.getOrNull(3)?.toLongOrNull()
                if (start != existing || total != spec.bytes) {
                    part.delete()
                    connection.disconnect()
                    connection = null
                    downloadFile(bundle, spec, task, operationId)
                    return
                }
            }
            if (!append) existing = 0
            val expectedResponseBytes = if (append) spec.bytes - existing else spec.bytes
            val responseBytes = connection.contentLengthLong
            if (responseBytes >= 0 && responseBytes != expectedResponseBytes) {
                throw IOException("下载响应长度不正确，预期=$expectedResponseBytes，实际=$responseBytes")
            }
            val buffer = ByteArray(64 * 1024)
            var lastUpdateAt = System.currentTimeMillis()
            var lastUpdateBytes = presentBytes(bundle)
            connection.inputStream.use { input ->
                FileOutputStream(part, append).buffered().use { output ->
                    while (true) {
                        checkTask(task)
                        val count = input.read(buffer)
                        if (count < 0) break
                        if (count == 0) continue
                        output.write(buffer, 0, count)
                        val now = System.currentTimeMillis()
                        if (now - lastUpdateAt >= 350) {
                            val current = presentBytes(bundle)
                            val speed = ((current - lastUpdateBytes) * 1000L / (now - lastUpdateAt))
                                .coerceAtLeast(0)
                            val eta = if (speed > 0) ((bundle.totalBytes - current).coerceAtLeast(0) / speed) else 0
                            runtimeStates[bundle.id] = RuntimeState("downloading", speed, eta)
                            lastUpdateAt = now
                            lastUpdateBytes = current
                            notifyChanged()
                        }
                    }
                }
            }
            if (part.length() != spec.bytes) {
                throw IOException("下载字节数不完整，预期=${spec.bytes}，实际=${part.length()}")
            }
            runtimeStates[bundle.id] = RuntimeState("verifying")
            notifyChanged()
            if (sha256(part) != spec.sha256) {
                part.delete()
                throw IOException("SHA-256 校验失败：${spec.relativePath}")
            }
            promotePart(part, target)
            logger.info("模型文件下载并校验完成，资源=${bundle.id}，文件=${spec.relativePath}", operationId)
        } finally {
            connection?.disconnect()
        }
    }

    private fun buildState(spec: BundleSpec): ModelResourceState {
        val installed = isInstalled(spec)
        val runtime = runtimeStates[spec.id]
        val status = when {
            runtime != null -> runtime.status
            installed -> "available"
            else -> "missing"
        }
        val present = presentBytes(spec)
        val installedBytes = if (installed) spec.totalBytes else 0L
        return ModelResourceState(
            id = spec.id,
            name = spec.name,
            purpose = spec.purpose,
            version = spec.version,
            totalBytes = spec.totalBytes,
            presentBytes = present,
            installedBytes = installedBytes,
            status = status,
            speedBytesPerSecond = runtime?.speed ?: 0,
            etaSeconds = runtime?.eta ?: 0,
            freeBytes = rootDirectory().usableSpace,
            errorMessage = runtime?.error.orEmpty()
        )
    }

    private fun remainingDownloadBytes(spec: BundleSpec): Long = spec.files.sumOf { file ->
        val target = safeFile(bundleDirectory(spec.id), file.relativePath)
        if (target.length() == file.bytes && sha256(target) == file.sha256) {
            0L
        } else {
            if (target.exists() && !target.delete()) {
                throw IOException("无法清理无效的模型文件：${file.relativePath}")
            }
            val part = File(target.parentFile, "${target.name}.part")
            (file.bytes - part.length().coerceAtMost(file.bytes)).coerceAtLeast(0L)
        }
    }

    private fun isInstalled(spec: BundleSpec): Boolean {
        val marker = File(bundleRoot(spec), ".installed-version")
        if (!marker.exists() || runCatching { marker.readText(Charsets.UTF_8).trim() }.getOrNull() != spec.version) {
            return false
        }
        return spec.files.all { safeFile(bundleDirectory(spec.id), it.relativePath).length() == it.bytes }
    }

    private fun presentBytes(spec: BundleSpec): Long = spec.files.sumOf { file ->
        val target = safeFile(bundleDirectory(spec.id), file.relativePath)
        when {
            target.length() == file.bytes -> file.bytes
            else -> File(target.parentFile, "${target.name}.part").length().coerceAtMost(file.bytes)
        }
    }

    private fun writeMarker(spec: BundleSpec) {
        val directory = bundleRoot(spec).apply { mkdirs() }
        val part = File(directory, ".installed-version.part")
        val marker = File(directory, ".installed-version")
        part.writeText(spec.version + "\n", Charsets.UTF_8)
        try {
            Files.move(
                part.toPath(),
                marker.toPath(),
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING
            )
        } catch (_: Exception) {
            Files.move(part.toPath(), marker.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
    }

    private fun promotePart(part: File, target: File) {
        try {
            Files.move(
                part.toPath(),
                target.toPath(),
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING
            )
        } catch (_: Exception) {
            Files.move(part.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
    }

    private fun checkTask(task: DownloadTask) {
        if (task.cancelled.get()) throw DownloadCancelled()
        if (task.paused.get()) throw DownloadPaused()
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                if (count > 0) digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun safeFile(parent: File, relativePath: String): File {
        val target = File(parent, relativePath).canonicalFile
        val canonicalParent = parent.canonicalFile
        require(target.path.startsWith(canonicalParent.path + File.separator)) { "无效资源路径" }
        return target
    }

    private fun readCatalog(): List<BundleSpec> {
        val text = app.assets.open("model-resources.json").bufferedReader(Charsets.UTF_8).use { it.readText() }
        val resources = JSONObject(text).getJSONArray("resources")
        val seenIds = mutableSetOf<String>()
        return buildList {
            for (resourceIndex in 0 until resources.length()) {
                val resource = resources.getJSONObject(resourceIndex)
                val id = resource.getString("id")
                val version = resource.getString("version")
                require(isSafeComponent(id)) { "模型资源编号不安全" }
                require(isSafeComponent(version)) { "模型资源版本不安全" }
                require(seenIds.add(id)) { "模型资源编号重复" }
                val files = resource.getJSONArray("files")
                val seenFiles = mutableSetOf<String>()
                val parsedFiles = buildList {
                    for (fileIndex in 0 until files.length()) {
                        val file = files.getJSONObject(fileIndex)
                        val relativePath = file.getString("path")
                        val url = file.getString("url")
                        val bytes = file.getLong("bytes")
                        val sha256 = file.getString("sha256").lowercase()
                        require(isSafeRelativePath(relativePath)) { "模型资源文件路径不安全" }
                        require(seenFiles.add(relativePath)) { "模型资源文件路径重复" }
                        require(URL(url).protocol.equals("https", ignoreCase = true)) {
                            "模型下载地址必须使用 HTTPS"
                        }
                        require(bytes > 0) { "模型资源文件大小必须为正数" }
                        require(sha256.matches(Regex("[0-9a-f]{64}"))) { "模型资源 SHA-256 不正确" }
                        add(
                            FileSpec(
                                relativePath = relativePath,
                                url = url,
                                bytes = bytes,
                                sha256 = sha256
                            )
                        )
                    }
                }
                add(
                    BundleSpec(
                        id = id,
                        name = resource.getString("name"),
                        purpose = resource.getString("purpose"),
                        version = version,
                        files = parsedFiles
                    )
                )
            }
        }
    }

    private fun rootDirectory(): File {
        ensureInitialized()
        return File(app.noBackupFilesDir, "resource-packs")
    }

    private fun bundleRoot(spec: BundleSpec): File = safeFile(rootDirectory(), spec.id)

    private fun versionDirectory(spec: BundleSpec): File = safeFile(bundleRoot(spec), spec.version)

    private fun cleanupOldVersions(spec: BundleSpec) {
        val resourceRoot = bundleRoot(spec).canonicalFile
        val current = versionDirectory(spec).canonicalFile
        resourceRoot.listFiles().orEmpty()
            .filter { it.isDirectory && it.canonicalFile != current }
            .forEach { old ->
                val candidate = old.canonicalFile
                if (candidate.parentFile == resourceRoot && !candidate.deleteRecursively()) {
                    logger.warning("旧模型版本目录未能完全清理，资源=${spec.id}", "model-cleanup")
                }
            }
    }

    private fun isSafeComponent(value: String): Boolean =
        value.isNotBlank() && value != "." && value != ".." &&
            value.all { it.isLetterOrDigit() || it in setOf('.', '_', '-') }

    private fun isSafeRelativePath(value: String): Boolean =
        value.isNotBlank() && !value.startsWith('/') && !value.startsWith('\\') &&
            value.split('/', '\\').all(::isSafeComponent)

    private fun bundle(id: String): BundleSpec? = bundles.firstOrNull { it.id == id }

    private fun ensureInitialized() {
        check(::app.isInitialized) { "ModelResourceManager 尚未初始化" }
    }

    private fun notifyChanged() {
        if (!::app.isInitialized) return
        val snapshot = states()
        main.post { listeners.forEach { it.onModelResourcesChanged(snapshot) } }
    }

    private const val MINIMUM_FREE_BYTES = 64L * 1024 * 1024
    private val CONTENT_RANGE = Regex("bytes\\s+(\\d+)-(\\d+)/(\\d+)", RegexOption.IGNORE_CASE)
}
