package com.smyongbu.voiceinput

import android.content.Context

object OverlayPreferences {
    private const val STORE = "overlay_appearance"
    private const val TEXT_ENABLED = "text_enabled"
    private const val OPACITY = "opacity_percent"
    const val DEFAULT_OPACITY = 72

    fun textEnabled(context: Context): Boolean = preferences(context).getBoolean(TEXT_ENABLED, true)

    fun setTextEnabled(context: Context, enabled: Boolean) {
        preferences(context).edit().putBoolean(TEXT_ENABLED, enabled).apply()
    }

    fun opacity(context: Context): Int = preferences(context)
        .getInt(OPACITY, DEFAULT_OPACITY)
        .coerceIn(35, 100)

    fun setOpacity(context: Context, percent: Int) {
        preferences(context).edit().putInt(OPACITY, percent.coerceIn(35, 100)).apply()
    }

    private fun preferences(context: Context) =
        context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
}
