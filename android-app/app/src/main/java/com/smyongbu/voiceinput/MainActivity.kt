package com.smyongbu.voiceinput

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import android.view.View
import android.widget.*

class MainActivity : Activity(), RecognitionController.Listener {
    private lateinit var statusText: TextView; private lateinit var transcriptText: TextView
    private lateinit var recordButton: Button; private lateinit var overlayButton: Button; private lateinit var waveform: WaveformView
    override fun onCreate(state: android.os.Bundle?) {
        super.onCreate(state); setContentView(R.layout.activity_main);applySystemInsets(findViewById(R.id.mainRoot)); RecognitionController.init(this)
        statusText=findViewById(R.id.statusText);transcriptText=findViewById(R.id.transcriptText);recordButton=findViewById(R.id.recordButton);overlayButton=findViewById(R.id.overlayButton);waveform=findViewById(R.id.waveform)
        val selected=RecognitionController.selectedEngine(); val radioId=when(selected){RecognitionController.ENGINE_ZIPFORMER->R.id.zipformerOption;RecognitionController.ENGINE_PARAFORMER->R.id.paraformerOption;RecognitionController.ENGINE_SYSTEM->R.id.systemOption;else->R.id.dualOption};findViewById<RadioButton>(radioId).isChecked=true
        findViewById<RadioGroup>(R.id.engineGroup).setOnCheckedChangeListener { _,id-> val engine=when(id){R.id.zipformerOption->RecognitionController.ENGINE_ZIPFORMER;R.id.paraformerOption->RecognitionController.ENGINE_PARAFORMER;R.id.systemOption->RecognitionController.ENGINE_SYSTEM;else->RecognitionController.ENGINE_DUAL};RecognitionController.setEngine(engine);statusText.text=engineDescription(engine) }
        recordButton.setOnClickListener{ensureAudio{RecognitionController.toggle()}};overlayButton.setOnClickListener{toggleOverlay()};findViewById<Button>(R.id.copyButton).setOnClickListener{copyText(transcriptText.text.toString())};findViewById<Button>(R.id.historyButton).setOnClickListener{startActivity(Intent(this,HistoryActivity::class.java))};showDevicePerformance();updateOverlay()
    }
    private fun engineDescription(e:String)=when(e){RecognitionController.ENGINE_ZIPFORMER->"已选择 Zipformer：速度优先";RecognitionController.ENGINE_PARAFORMER->"已选择 Paraformer：停止后整段识别";RecognitionController.ENGINE_SYSTEM->"已选择手机系统默认识别";else->"已选择双模型：实时识别并在停止后整体校正"}
    private fun ensureAudio(action:()->Unit){if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED)action()else requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO),1001)}
    private fun toggleOverlay(){if(!Settings.canDrawOverlays(this)){startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")));return};ensureAudio{val i=Intent(this,FloatingVoiceService::class.java);if(FloatingVoiceService.isRunning)stopService(i)else startForegroundService(i);overlayButton.postDelayed({updateOverlay()},250)}}
    private fun updateOverlay(){overlayButton.text=if(FloatingVoiceService.isRunning)"关闭悬浮小球" else "开启悬浮小球"}
    private fun copyText(raw:String){val text=raw.trim();if(text.isBlank()||text=="识别文字会显示在这里"){Toast.makeText(this,"还没有可以复制的文字。",Toast.LENGTH_SHORT).show();return};(getSystemService(CLIPBOARD_SERVICE)as android.content.ClipboardManager).setPrimaryClip(ClipData.newPlainText("语音识别文字",text));Toast.makeText(this,"已复制到剪贴板。",Toast.LENGTH_SHORT).show()}
    private fun showDevicePerformance(){val info=android.app.ActivityManager.MemoryInfo();(getSystemService(ACTIVITY_SERVICE)as android.app.ActivityManager).getMemoryInfo(info);val gb=kotlin.math.round(info.totalMem/1073741824.0).toInt();val rating=when{gb>=8->"适合使用推荐的双模型方案";gb>=6->"可以使用双模型，长时间录音时建议关闭其他大型应用";else->"建议优先使用仅 Zipformer 方案"};findViewById<TextView>(R.id.performanceText).text="本机约 ${gb} GB 内存：$rating。\n\nZipformer：模型 26 MB；最低 4 核处理器、4 GB 内存，推荐 6 GB；常驻内存估算 150～250 MB。\n\nParaformer：模型 82 MB；最低 4 核处理器、4 GB 内存，推荐 8 GB；校正时内存估算 250～450 MB。\n\n双模型：最低 6 GB 内存，推荐 8 GB 以上；合计常驻内存估算 400～700 MB。软件打开后会后台预加载，进程存活期间不会重复加载。\n\n以上为保守估算，实际占用随录音长度和系统负载变化。"}
    override fun onRecognitionState(listening:Boolean,status:String,text:String)=runOnUiThread{statusText.text=status;if(text.isNotBlank())transcriptText.text=text;recordButton.text=if(listening)"停止识别" else "开始识别";waveform.visibility=if(listening)View.VISIBLE else View.INVISIBLE}
    override fun onAudioLevel(level:Float)=runOnUiThread{waveform.setLevel(level)}
    override fun onResume(){super.onResume();RecognitionController.addListener(this);updateOverlay()};override fun onPause(){RecognitionController.removeListener(this);super.onPause()}
    override fun onRequestPermissionsResult(code:Int,permissions:Array<out String>,results:IntArray){super.onRequestPermissionsResult(code,permissions,results);if(code==1001)Toast.makeText(this,if(results.firstOrNull()==PackageManager.PERMISSION_GRANTED)"麦克风权限已允许，请再次点击。" else "需要麦克风权限才能识别。",Toast.LENGTH_LONG).show()}
}
