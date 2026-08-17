package com.smyongbu.voiceinput

import android.content.Context
import android.os.Handler
import android.os.Looper
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
    const val ZIPFORMER_ID = "zipformer-bilingual"
    const val PARAFORMER_ID = "paraformer"

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
            id = ZIPFORMER_ID,
            name = "中英双语实时模型",
            purpose = "边说边显示中文、英文和中英混说结果",
            version = "2024-03-20-exp32-int8",
            files = listOf(
                FileSpec(
                    "encoder-epoch-99-avg-1.int8.onnx",
                    "https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/resolve/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3/exp/32/encoder-epoch-99-avg-1.int8.onnx",
                    42_980_793,
                    "db6f51551762e40e549166fe041ea3e45464370b595e9ad23f06478ec3794fbb"
                ),
                FileSpec(
                    "decoder-epoch-99-avg-1.onnx",
                    "https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/resolve/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3/exp/32/decoder-epoch-99-avg-1.onnx",
                    13_877_276,
                    "89be509a83175261695bdef5fd1c7b9ab1129a663d1284e7ba9f8507b21e0906"
                ),
                FileSpec(
                    "joiner-epoch-99-avg-1.int8.onnx",
                    "https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/resolve/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3/exp/32/joiner-epoch-99-avg-1.int8.onnx",
                    3_228_485,
                    "bdda356d6f9b8c2d7cee9ee0e26075fa537490f7fd06520be408d287073667b9"
                ),
                FileSpec(
                    "tokens.txt",
                    "https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/resolve/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3/data/lang_char_bpe/tokens.txt",
                    56_317,
                    "a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3"
                )
            )
        ),
        BundleSpec(
            id = PARAFORMER_ID,
            name = "中英双语整段校正模型",
            purpose = "停止后重新校正完整句子，改善长句连贯度",
            version = "2024-03-09-small-int8",
            files = listOf(
                FileSpec(
                    "model.int8.onnx",
                    "https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-small-2024-03-09/resolve/63ddc3cd0f2810b68289a7b3876e62ef5d53d6df/model.int8.onnx",
                    81_828_675,
                    "3ef6c19369b912f7caf3cef8e545c5ccd1a33d9d7ec792a46668dc41c4b229ec"
                ),
                FileSpec(
                    "tokens.txt",
                    "https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-small-2024-03-09/resolve/63ddc3cd0f2810b68289a7b3876e62ef5d53d6df/tokens.txt",
                    75_352,
                    "4b2d964e18b9cf139b473003b6698fb2ed9a2a5ec55b93daa677b28f578897aa"
                )
            )
        )
    )

    private val listeners = CopyOnWriteArrayList<Listener>()
    private val runtimeStates = ConcurrentHashMap<String, RuntimeState>()
    private val tasks = ConcurrentHashMap<String, DownloadTask>()
    private val taskExecutor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private lateinit var app: Context
    private lateinit var logger: AppLogger
    private lateinit var bundles: List<BundleSpec>

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
            bundles.filter(::isInstalled).forEach(::cleanupOldVersions)
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
