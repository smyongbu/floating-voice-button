package com.smyongbu.voiceinput

import android.content.Context

object OverlayPreferences {
    private const val STORE = "overlay_appearance"
    private const val TEXT_ENABLED = "text_enabled"
    private const val OPACITY = "opacity_percent"
    private const val SIZE = "size_dp"
    private const val POSITION_SIDE = "position_side"
    private const val POSITION_Y = "position_y"
    const val DEFAULT_OPACITY = 72
    const val DEFAULT_SIZE = 64

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

    fun size(context: Context): Int = preferences(context)
        .getInt(SIZE, DEFAULT_SIZE)
        .coerceIn(48, 88)

    fun setSize(context: Context, sizeDp: Int) {
        preferences(context).edit().putInt(SIZE, sizeDp.coerceIn(48, 88)).apply()
    }

    internal fun position(context: Context): FloatingOverlayGeometry.StoredPosition? {
        val values = preferences(context)
        if (!values.contains(POSITION_SIDE) || !values.contains(POSITION_Y)) return null
        val side = values.getString(POSITION_SIDE, null)
            ?.let { runCatching { FloatingOverlayGeometry.Side.valueOf(it) }.getOrNull() }
            ?: return null
        return FloatingOverlayGeometry.StoredPosition(
            side = side,
            normalizedY = values.getFloat(POSITION_Y, 0.5f).coerceIn(0f, 1f),
        )
    }

    internal fun setPosition(context: Context, position: FloatingOverlayGeometry.StoredPosition) {
        preferences(context).edit()
            .putString(POSITION_SIDE, position.side.name)
            .putFloat(POSITION_Y, position.normalizedY.coerceIn(0f, 1f))
            .apply()
    }

    private fun preferences(context: Context) =
        context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
}
