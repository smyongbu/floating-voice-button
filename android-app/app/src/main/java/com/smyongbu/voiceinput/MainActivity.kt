package com.smyongbu.voiceinput

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity(), RecognitionController.Listener {
    private lateinit var statusText: TextView
    private lateinit var transcriptText: TextView
    private lateinit var recordButton: Button
    private lateinit var waveform: WaveformView

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        setContentView(R.layout.activity_main)
        applySystemInsets(findViewById(R.id.mainRoot))
        setupBottomNavigation(NAV_RECORDING)
        RecognitionController.init(this)
        statusText = findViewById(R.id.statusText)
        transcriptText = findViewById(R.id.transcriptText)
        recordButton = findViewById(R.id.recordButton)
        waveform = findViewById(R.id.waveform)
        recordButton.setOnClickListener { ensureAudio { RecognitionController.toggle() } }
        findViewById<Button>(R.id.copyButton).setOnClickListener { copyText(transcriptText.text.toString()) }
    }

    private fun ensureAudio(action: () -> Unit) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) action()
        else requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO)
    }

    private fun copyText(raw: String) {
        val text = raw.trim()
        if (text.isBlank() || text == "识别文字会显示在这里") {
            Toast.makeText(this, "还没有可以复制的文字。", Toast.LENGTH_SHORT).show()
            return
        }
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("语音识别文字", text))
        Toast.makeText(this, "已复制到剪贴板。", Toast.LENGTH_SHORT).show()
    }

    override fun onRecognitionState(listening: Boolean, status: String, text: String) = runOnUiThread {
        statusText.text = status
        if (text.isNotBlank()) transcriptText.text = text
        recordButton.text = if (listening) "停止识别" else "开始识别"
        waveform.visibility = if (listening) View.VISIBLE else View.GONE
        if (!listening) waveform.reset()
    }

    override fun onAudioLevel(level: Float) = runOnUiThread {
        if (waveform.visibility == View.VISIBLE) waveform.setLevel(level)
    }

    override fun onResume() { super.onResume(); RecognitionController.addListener(this) }
    override fun onPause() { RecognitionController.removeListener(this); super.onPause() }

    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, permissions, results)
        if (code == REQUEST_AUDIO) {
            val message = if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED) "麦克风权限已允许，请再次点击开始识别。" else "需要麦克风权限才能识别。"
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        }
    }

    companion object { private const val REQUEST_AUDIO = 1001 }
}
