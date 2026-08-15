package com.smyongbu.voiceinput

import android.app.Activity
import android.os.Build
import android.view.View
import android.view.WindowInsets

fun Activity.applySystemInsets(root: View) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) window.setDecorFitsSystemWindows(false)
    val initialLeft = root.paddingLeft
    val initialTop = root.paddingTop
    val initialRight = root.paddingRight
    val initialBottom = root.paddingBottom
    root.setOnApplyWindowInsetsListener { view, insets ->
        val left: Int
        val top: Int
        val right: Int
        val bottom: Int
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val safe = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            left = safe.left
            top = safe.top
            right = safe.right
            bottom = safe.bottom
        } else {
            @Suppress("DEPRECATION")
            left = insets.systemWindowInsetLeft
            @Suppress("DEPRECATION")
            top = insets.systemWindowInsetTop
            @Suppress("DEPRECATION")
            right = insets.systemWindowInsetRight
            @Suppress("DEPRECATION")
            bottom = insets.systemWindowInsetBottom
        }
        view.setPadding(initialLeft + left, initialTop + top, initialRight + right, initialBottom + bottom)
        insets
    }
    root.requestApplyInsets()
}
