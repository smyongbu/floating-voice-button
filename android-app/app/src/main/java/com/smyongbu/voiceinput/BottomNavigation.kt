package com.smyongbu.voiceinput

import android.app.Activity
import android.content.Intent
import android.content.res.ColorStateList
import android.os.Build
import android.widget.Button

const val NAV_RECOGNITION = 1
const val NAV_HISTORY = 2

fun Activity.setupBottomNavigation(current: Int) {
    val recognition = findViewById<Button>(R.id.navRecognition)
    val history = findViewById<Button>(R.id.navHistory)
    styleNavigationItem(recognition, current == NAV_RECOGNITION)
    styleNavigationItem(history, current == NAV_HISTORY)
    recognition.setOnClickListener {
        if (current != NAV_RECOGNITION) {
            AppLogger(this).info("底部导航切换到语音识别")
            startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
            finish()
        }
    }
    history.setOnClickListener {
        if (current != NAV_HISTORY) {
            AppLogger(this).info("底部导航切换到识别历史")
            startActivity(Intent(this, HistoryActivity::class.java))
        }
    }
}

private fun Activity.styleNavigationItem(button: Button, selected: Boolean) {
    button.isSelected = selected
    button.background = getDrawable(if (selected) R.drawable.nav_item_selected else R.drawable.nav_item_unselected)
    val color = getColor(if (selected) R.color.nav_selected else R.color.nav_unselected)
    button.setTextColor(color)
    button.compoundDrawableTintList = ColorStateList.valueOf(color)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) button.stateDescription = if (selected) "当前页面" else null
}
