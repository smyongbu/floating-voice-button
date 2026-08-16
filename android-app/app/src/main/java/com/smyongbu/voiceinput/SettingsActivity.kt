package com.smyongbu.voiceinput

import android.Manifest
import android.app.Activity
import android.app.ActivityManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import kotlin.math.round

class SettingsActivity : Activity() {
    private lateinit var overlaySwitch: Switch
    private lateinit var overlayStatus: TextView
    private var updatingSwitch = false
    private var waitingForOverlayPermission = false

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        setContentView(R.layout.activity_settings)
        applySystemInsets(findViewById(R.id.settingsRoot))
        setupBottomNavigation(NAV_SETTINGS)
        RecognitionController.init(this)
        setupRecognitionOptions()
        showDevicePerformance()
        overlaySwitch = findViewById(R.id.overlaySwitch)
        overlayStatus = findViewById(R.id.overlayStatus)
        overlaySwitch.setOnCheckedChangeListener { _, checked ->
            if (!updatingSwitch) changeOverlay(checked)
        }
    }

    private fun setupRecognitionOptions() {
        val selected = RecognitionController.selectedEngine()
        val radioId = when (selected) {
            RecognitionController.ENGINE_ZIPFORMER -> R.id.zipformerOption
            RecognitionController.ENGINE_PARAFORMER -> R.id.paraformerOption
            RecognitionController.ENGINE_SYSTEM -> R.id.systemOption
            else -> R.id.dualOption
        }
        findViewById<RadioButton>(radioId).isChecked = true
        findViewById<RadioGroup>(R.id.engineGroup).setOnCheckedChangeListener { _, id ->
            val engine = when (id) {
                R.id.zipformerOption -> RecognitionController.ENGINE_ZIPFORMER
                R.id.paraformerOption -> RecognitionController.ENGINE_PARAFORMER
                R.id.systemOption -> RecognitionController.ENGINE_SYSTEM
                else -> RecognitionController.ENGINE_DUAL
            }
            RecognitionController.setEngine(engine)
            AppLogger(this).info("识别方案已更改")
            Toast.makeText(this, "识别方案已保存。", Toast.LENGTH_SHORT).show()
        }
    }

    private fun changeOverlay(enabled: Boolean) {
        if (!enabled) {
            waitingForOverlayPermission = false
            stopService(Intent(this, FloatingVoiceService::class.java))
            AppLogger(this).info("用户关闭悬浮小球")
            overlaySwitch.postDelayed({ updateOverlayState() }, 180)
            return
        }
        if (!Settings.canDrawOverlays(this)) {
            waitingForOverlayPermission = true
            setSwitchChecked(false)
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            return
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            setSwitchChecked(false)
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO)
            return
        }
        startForegroundService(Intent(this, FloatingVoiceService::class.java))
        AppLogger(this).info("用户开启悬浮小球")
        overlaySwitch.postDelayed({ updateOverlayState() }, 180)
    }

    private fun updateOverlayState() {
        setSwitchChecked(FloatingVoiceService.isRunning)
        overlayStatus.text = if (FloatingVoiceService.isRunning) {
            "悬浮小球已开启；点击开始或停止识别，长按可关闭。"
        } else {
            "开启后可在其他应用上方开始识别。"
        }
    }

    private fun setSwitchChecked(checked: Boolean) {
        updatingSwitch = true
        overlaySwitch.isChecked = checked
        updatingSwitch = false
    }

    private fun showDevicePerformance() {
        val info = ActivityManager.MemoryInfo()
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(info)
        val gb = round(info.totalMem / 1073741824.0).toInt()
        val rating = when {
            gb >= 8 -> "适合使用推荐的双模型方案"
            gb >= 6 -> "可以使用双模型，长时间录音时建议关闭其他大型应用"
            else -> "建议优先使用仅 Zipformer 方案"
        }
        findViewById<TextView>(R.id.performanceText).text =
            "本机约 ${gb} GB 内存：$rating。模型会在应用启动后预加载并常驻内存；性能数据为保守估算。"
    }

    override fun onResume() {
        super.onResume()
        if (waitingForOverlayPermission && Settings.canDrawOverlays(this)) {
            waitingForOverlayPermission = false
            changeOverlay(true)
        } else {
            updateOverlayState()
        }
    }

    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, permissions, results)
        if (code == REQUEST_AUDIO) {
            if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED) changeOverlay(true)
            else Toast.makeText(this, "需要麦克风权限才能使用悬浮识别。", Toast.LENGTH_LONG).show()
        }
    }

    companion object { private const val REQUEST_AUDIO = 2001 }
}
