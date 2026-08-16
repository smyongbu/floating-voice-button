package com.smyongbu.voiceinput

import android.app.Activity
import android.content.Intent
import android.content.res.ColorStateList
import android.os.Build
import android.widget.Button

const val NAV_RECORDING = 1
const val NAV_HISTORY = 2
const val NAV_SETTINGS = 3

fun Activity.setupBottomNavigation(current: Int) {
    val recording = findViewById<Button>(R.id.navRecording)
    val history = findViewById<Button>(R.id.navHistory)
    val settings = findViewById<Button>(R.id.navSettings)
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
    finish()
}

private fun Activity.styleNavigationItem(button: Button, selected: Boolean) {
    button.isSelected = selected
    button.background = getDrawable(if (selected) R.drawable.nav_item_selected else R.drawable.nav_item_unselected)
    val color = getColor(if (selected) R.color.nav_selected else R.color.nav_unselected)
    button.setTextColor(color)
    button.compoundDrawableTintList = ColorStateList.valueOf(color)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) button.stateDescription = if (selected) "当前页面" else null
}
