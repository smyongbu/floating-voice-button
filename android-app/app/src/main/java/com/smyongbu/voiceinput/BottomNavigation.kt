package com.smyongbu.voiceinput

import android.app.Activity
import android.content.Intent
import android.content.res.ColorStateList
import android.os.Build
import android.view.View
import android.widget.TextView

const val NAV_RECORDING = 1
const val NAV_HISTORY = 2
const val NAV_SETTINGS = 3

fun Activity.setupBottomNavigation(current: Int) {
    val recording = findViewById<TextView>(R.id.navRecording)
    val history = findViewById<TextView>(R.id.navHistory)
    val settings = findViewById<TextView>(R.id.navSettings)
    styleNavigationItem(recording, current == NAV_RECORDING)
    styleNavigationItem(history, current == NAV_HISTORY)
    styleNavigationItem(settings, current == NAV_SETTINGS)
    recording.setOnClickListener { if (current != NAV_RECORDING) openTopLevel(MainActivity::class.java, "录音") }
    history.setOnClickListener { if (current != NAV_HISTORY) openTopLevel(HistoryActivity::class.java, "记录") }
    settings.setOnClickListener { if (current != NAV_SETTINGS) openTopLevel(SettingsActivity::class.java, "设置") }
}

private fun Activity.openTopLevel(target: Class<out Activity>, label: String) {
    AppLogger(this).info("底部导航切换到$label")
    startActivity(Intent(this, target).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
    @Suppress("DEPRECATION")
    overridePendingTransition(0, 0)
    finish()
}

private fun Activity.styleNavigationItem(item: TextView, selected: Boolean) {
    item.isSelected = selected
    item.background = getDrawable(if (selected) R.drawable.nav_item_selected else R.drawable.nav_item_unselected)
    val color = getColor(if (selected) R.color.nav_selected else R.color.nav_unselected)
    item.setTextColor(color)
    item.compoundDrawableTintList = ColorStateList.valueOf(color)
    item.setTypeface(item.typeface, if (selected) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
    item.animate().cancel()
    if (selected) {
        item.alpha = 0.72f
        item.scaleX = 0.96f
        item.scaleY = 0.96f
        item.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(180L)
            .setInterpolator(android.view.animation.DecelerateInterpolator()).start()
    } else {
        item.alpha = 1f
        item.scaleX = 1f
        item.scaleY = 1f
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) item.stateDescription = if (selected) "当前页面" else null
    item.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
}
