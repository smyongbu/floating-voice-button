package com.smyongbu.voiceinput

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

data class HistoryItem(val id: Long, val text: String, val createdAt: String, val engine: String)

class HistoryStore(context: Context) : SQLiteOpenHelper(context, "识别历史.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase) { db.execSQL("CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, engine TEXT NOT NULL)") }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit
    @Synchronized fun add(text: String, engine: String) {
        writableDatabase.execSQL("INSERT INTO history(text,engine) VALUES(?,?)", arrayOf(text.trim(), engine))
        writableDatabase.execSQL("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 500)")
    }
    @Synchronized fun list(limit: Int = 100): List<HistoryItem> {
        val result = mutableListOf<HistoryItem>()
        readableDatabase.rawQuery("SELECT id,text,created_at,engine FROM history ORDER BY id DESC LIMIT ?", arrayOf(limit.coerceIn(1,500).toString())).use { c ->
            while (c.moveToNext()) result += HistoryItem(c.getLong(0), c.getString(1), c.getString(2), c.getString(3))
        }; return result
    }
    @Synchronized fun get(id: Long): HistoryItem? {
        readableDatabase.rawQuery(
            "SELECT id,text,created_at,engine FROM history WHERE id=? LIMIT 1",
            arrayOf(id.toString())
        ).use { c ->
            return if (c.moveToFirst()) HistoryItem(c.getLong(0), c.getString(1), c.getString(2), c.getString(3)) else null
        }
    }
    @Synchronized fun clear() { writableDatabase.delete("history", null, null) }
    @Synchronized fun delete(id: Long) { writableDatabase.delete("history", "id=?", arrayOf(id.toString())) }
}
