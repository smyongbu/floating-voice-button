package com.smyongbu.voiceinput

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.io.File
import java.io.IOException
import java.util.UUID

enum class TestSelectedResult(val wireValue: String) {
    REALTIME_DRAFT("realtime_draft"),
    SECOND_PASS("second_pass"),
    SINGLE_RESULT("single_result");

    companion object {
        fun fromWireValue(value: String?): TestSelectedResult =
            values().firstOrNull { it.wireValue == value } ?: SINGLE_RESULT
    }
}

data class HistoryTestData(
    val realtimeDraft: String,
    val secondPassText: String?,
    val selectedResult: TestSelectedResult,
    val audioAvailable: Boolean,
    val durationMs: Long,
    val audioBytes: Long,
)

data class HistoryItem(
    val id: Long,
    val text: String,
    val createdAt: String,
    val engine: String,
    val test: HistoryTestData? = null,
)

object RecognitionTestMode {
    const val PREFERENCES_NAME = "settings"
    const val KEY_ENABLED = "test_mode_enabled"

    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_ENABLED, false)

    fun setEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ENABLED, enabled)
            .apply()
    }
}

class HistoryStore(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {
    private val appContext = context.applicationContext
    private val audioDirectory = File(appContext.filesDir, AUDIO_DIRECTORY_NAME)

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                engine TEXT NOT NULL,
                test_realtime_draft TEXT,
                test_second_pass_text TEXT,
                test_selected_result TEXT,
                test_audio_file TEXT,
                test_audio_duration_ms INTEGER,
                test_audio_bytes INTEGER
            )
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            db.execSQL("ALTER TABLE history ADD COLUMN test_realtime_draft TEXT")
            db.execSQL("ALTER TABLE history ADD COLUMN test_second_pass_text TEXT")
            db.execSQL("ALTER TABLE history ADD COLUMN test_selected_result TEXT")
            db.execSQL("ALTER TABLE history ADD COLUMN test_audio_file TEXT")
            db.execSQL("ALTER TABLE history ADD COLUMN test_audio_duration_ms INTEGER")
            db.execSQL("ALTER TABLE history ADD COLUMN test_audio_bytes INTEGER")
        }
    }

    @Synchronized
    fun add(text: String, engine: String): Long = insertWithPruning(
        ContentValues().apply {
            put("text", text.trim())
            put("engine", engine)
        }
    )

    @Synchronized
    fun addWithTestData(
        finalText: String,
        engine: String,
        realtimeDraft: String,
        secondPassText: String?,
        selectedResult: TestSelectedResult,
        audioSamples: FloatArray,
        sampleRateHz: Int = DEFAULT_SAMPLE_RATE_HZ,
    ): Long {
        if (!RecognitionTestMode.isEnabled(appContext)) return add(finalText, engine)

        val cleanFinalText = finalText.trim()
        val cleanRealtimeDraft = realtimeDraft.trim().ifBlank { cleanFinalText }
        val cleanSecondPass = secondPassText?.trim()?.takeIf { it.isNotBlank() }
        val cleanSelectedResult = if (
            selectedResult == TestSelectedResult.SECOND_PASS && cleanSecondPass == null
        ) {
            TestSelectedResult.REALTIME_DRAFT
        } else {
            selectedResult
        }
        var finalAudioFile: File? = null
        var temporaryAudioFile: File? = null

        try {
            val wavInfo = if (audioSamples.isNotEmpty()) {
                synchronized(FILE_LOCK) {
                    ensureAudioDirectory()
                    val token = UUID.randomUUID().toString().lowercase()
                    temporaryAudioFile = File(audioDirectory, "$token.wav.tmp")
                    finalAudioFile = File(audioDirectory, "$token.wav")
                    val info = PcmWavWriter.writeMono16(
                        file = temporaryAudioFile!!,
                        samples = audioSamples,
                        sampleRateHz = sampleRateHz,
                    )
                    if (!temporaryAudioFile!!.renameTo(finalAudioFile!!)) {
                        throw IOException("无法完成测试录音文件写入")
                    }
                    info
                }
            } else {
                null
            }

            return insertWithPruning(
                ContentValues().apply {
                    put("text", cleanFinalText)
                    put("engine", engine)
                    put("test_realtime_draft", cleanRealtimeDraft)
                    if (cleanSecondPass == null) putNull("test_second_pass_text")
                    else put("test_second_pass_text", cleanSecondPass)
                    put("test_selected_result", cleanSelectedResult.wireValue)
                    if (finalAudioFile == null || wavInfo == null) {
                        putNull("test_audio_file")
                        put("test_audio_duration_ms", 0L)
                        put("test_audio_bytes", 0L)
                    } else {
                        put("test_audio_file", finalAudioFile!!.name)
                        put("test_audio_duration_ms", wavInfo.durationMs)
                        put("test_audio_bytes", wavInfo.audioBytes)
                    }
                }
            )
        } catch (error: Throwable) {
            synchronized(FILE_LOCK) {
                runCatching { temporaryAudioFile?.delete() }
                runCatching { finalAudioFile?.delete() }
            }
            throw error
        } finally {
            synchronized(FILE_LOCK) {
                runCatching { temporaryAudioFile?.takeIf(File::exists)?.delete() }
            }
        }
    }

    @Synchronized
    fun list(limit: Int = 100): List<HistoryItem> {
        val result = mutableListOf<HistoryItem>()
        readableDatabase.rawQuery(
            "SELECT $HISTORY_COLUMNS FROM history ORDER BY id DESC LIMIT ?",
            arrayOf(limit.coerceIn(1, MAX_HISTORY_ITEMS).toString()),
        ).use { cursor ->
            while (cursor.moveToNext()) result += historyItem(cursor)
        }
        return result
    }

    @Synchronized
    fun get(id: Long): HistoryItem? {
        readableDatabase.rawQuery(
            "SELECT $HISTORY_COLUMNS FROM history WHERE id=? LIMIT 1",
            arrayOf(id.toString()),
        ).use { cursor ->
            return if (cursor.moveToFirst()) historyItem(cursor) else null
        }
    }

    @Synchronized
    fun audioFileForHistory(id: Long): File? {
        val fileName = readableDatabase.rawQuery(
            "SELECT test_audio_file FROM history WHERE id=? LIMIT 1",
            arrayOf(id.toString()),
        ).use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
        }
        return safeAudioFile(fileName)?.takeIf(File::isFile)
    }

    @Synchronized
    fun clear() {
        val audioFiles = storedAudioFileNames()
        writableDatabase.delete("history", null, null)
        deleteAudioFiles(audioFiles)
    }

    @Synchronized
    fun clearTestData() {
        val audioFiles = storedAudioFileNames()
        val values = ContentValues().apply {
            putNull("test_realtime_draft")
            putNull("test_second_pass_text")
            putNull("test_selected_result")
            putNull("test_audio_file")
            putNull("test_audio_duration_ms")
            putNull("test_audio_bytes")
        }
        writableDatabase.update(
            "history",
            values,
            "test_realtime_draft IS NOT NULL OR test_selected_result IS NOT NULL OR test_audio_file IS NOT NULL",
            null,
        )
        deleteAudioFiles(audioFiles)
    }

    @Synchronized
    fun delete(id: Long) {
        val audioFileName = readableDatabase.rawQuery(
            "SELECT test_audio_file FROM history WHERE id=? LIMIT 1",
            arrayOf(id.toString()),
        ).use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
        }
        writableDatabase.delete("history", "id=?", arrayOf(id.toString()))
        deleteAudioFiles(listOfNotNull(audioFileName))
    }

    @Synchronized
    fun cleanupUnreferencedAudioFiles(): Int = synchronized(FILE_LOCK) {
        if (!audioDirectory.exists()) return@synchronized 0
        val referenced = storedAudioFileNames().toHashSet()
        var deleted = 0
        audioDirectory.listFiles().orEmpty().forEach { candidate ->
            val safeWav = SAFE_AUDIO_NAME.matches(candidate.name)
            val staleTemporary = SAFE_TEMP_AUDIO_NAME.matches(candidate.name) &&
                System.currentTimeMillis() - candidate.lastModified() >= TEMP_FILE_STALE_MS
            if ((safeWav && candidate.name !in referenced) || staleTemporary) {
                if (candidate.delete()) deleted += 1
            }
        }
        deleted
    }

    private fun insertWithPruning(values: ContentValues): Long {
        val database = writableDatabase
        val prunedAudioFiles = mutableListOf<String>()
        var insertedId = -1L
        database.beginTransaction()
        try {
            insertedId = database.insertOrThrow("history", null, values)
            database.rawQuery(
                "SELECT id,test_audio_file FROM history ORDER BY id DESC LIMIT -1 OFFSET ?",
                arrayOf(MAX_HISTORY_ITEMS.toString()),
            ).use { cursor ->
                while (cursor.moveToNext()) {
                    val id = cursor.getLong(0)
                    if (!cursor.isNull(1)) prunedAudioFiles += cursor.getString(1)
                    database.delete("history", "id=?", arrayOf(id.toString()))
                }
            }
            database.setTransactionSuccessful()
        } finally {
            database.endTransaction()
        }
        deleteAudioFiles(prunedAudioFiles)
        return insertedId
    }

    private fun historyItem(cursor: Cursor): HistoryItem {
        val testDraft = if (cursor.isNull(4)) null else cursor.getString(4)
        val test = testDraft?.let {
            val audioFile = if (cursor.isNull(7)) null else safeAudioFile(cursor.getString(7))
            HistoryTestData(
                realtimeDraft = it,
                secondPassText = if (cursor.isNull(5)) null else cursor.getString(5),
                selectedResult = TestSelectedResult.fromWireValue(
                    if (cursor.isNull(6)) null else cursor.getString(6)
                ),
                audioAvailable = audioFile?.isFile == true,
                durationMs = if (cursor.isNull(8)) 0L else cursor.getLong(8).coerceAtLeast(0L),
                audioBytes = if (cursor.isNull(9)) 0L else cursor.getLong(9).coerceAtLeast(0L),
            )
        }
        return HistoryItem(
            id = cursor.getLong(0),
            text = cursor.getString(1),
            createdAt = cursor.getString(2),
            engine = cursor.getString(3),
            test = test,
        )
    }

    private fun storedAudioFileNames(): List<String> {
        val result = mutableListOf<String>()
        readableDatabase.rawQuery(
            "SELECT test_audio_file FROM history WHERE test_audio_file IS NOT NULL",
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) result += cursor.getString(0)
        }
        return result
    }

    private fun ensureAudioDirectory() {
        if (!audioDirectory.exists() && !audioDirectory.mkdirs()) {
            throw IOException("无法创建测试录音目录")
        }
        if (!audioDirectory.isDirectory) throw IOException("测试录音目录不可用")
    }

    private fun safeAudioFile(fileName: String?): File? {
        if (fileName == null || !SAFE_AUDIO_NAME.matches(fileName)) return null
        val root = runCatching { audioDirectory.canonicalFile }.getOrNull() ?: return null
        val candidate = runCatching { File(audioDirectory, fileName).canonicalFile }.getOrNull() ?: return null
        return candidate.takeIf { it.parentFile == root }
    }

    private fun deleteAudioFiles(fileNames: Collection<String>) {
        synchronized(FILE_LOCK) {
            fileNames.distinct().forEach { fileName ->
                safeAudioFile(fileName)?.takeIf(File::exists)?.delete()
            }
        }
    }

    companion object {
        private const val DATABASE_NAME = "识别历史.db"
        private const val DATABASE_VERSION = 2
        private const val MAX_HISTORY_ITEMS = 500
        private const val AUDIO_DIRECTORY_NAME = "test-recordings"
        private const val DEFAULT_SAMPLE_RATE_HZ = 16_000
        private const val TEMP_FILE_STALE_MS = 60L * 60L * 1000L
        private const val HISTORY_COLUMNS =
            "id,text,created_at,engine,test_realtime_draft,test_second_pass_text," +
                "test_selected_result,test_audio_file,test_audio_duration_ms,test_audio_bytes"
        private val SAFE_AUDIO_NAME =
            Regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.wav$")
        private val SAFE_TEMP_AUDIO_NAME =
            Regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.wav\\.tmp$")
        private val FILE_LOCK = Any()
    }
}
