package com.smyongbu.voiceinput

import android.app.*
import android.content.*
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.*
import android.view.*
import android.widget.*

class FloatingVoiceService : Service(), RecognitionController.Listener {
    companion object { @Volatile var isRunning=false; private const val CHANNEL="悬浮语音输入" }
    private lateinit var wm:WindowManager; private lateinit var ball:FloatingBallView
    private lateinit var logger:AppLogger
    private lateinit var caption:LinearLayout; private lateinit var captionText:TextView
    private lateinit var ballParams:WindowManager.LayoutParams; private lateinit var captionParams:WindowManager.LayoutParams
    private val handler=Handler(Looper.getMainLooper()); private var listening=false; private var level=0f
    private var manuallyHidden=false; private var previousListening=false

    override fun onCreate(){
        super.onCreate();isRunning=true;logger=AppLogger(this);RecognitionController.init(this);notifyForeground();wm=getSystemService(WINDOW_SERVICE)as WindowManager
        ball=FloatingBallView(this).apply{contentDescription="悬浮语音按钮。点击开始或停止，拖动改变位置，长按关闭。";elevation=dp(10).toFloat();isLongClickable=true}
        captionText=TextView(this).apply{textSize=15f;setTextColor(Color.rgb(15,23,42));maxLines=3;setPadding(dp(12),dp(8),dp(8),dp(8))}
        val close=Button(this).apply{text="关闭";isAllCaps=false;textSize=12f;contentDescription="关闭悬浮文字";setTextColor(Color.rgb(71,85,105));background=getDrawable(R.drawable.secondary_button);setOnClickListener{manuallyHidden=true;applyCaptionVisibility(false)}}
        caption=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL;background=GradientDrawable().apply{cornerRadius=dp(12).toFloat();setColor(Color.argb(246,255,255,255));setStroke(dp(1),Color.rgb(215,224,236))};addView(captionText,LinearLayout.LayoutParams(0,WindowManager.LayoutParams.WRAP_CONTENT,1f));addView(close,LinearLayout.LayoutParams(dp(64),dp(48)).apply{marginEnd=dp(6)})}
        ballParams=params(dp(58),dp(58),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE).apply{x=resources.displayMetrics.widthPixels-dp(78);y=resources.displayMetrics.heightPixels/2}
        val captionWidth=minOf(dp(330),resources.displayMetrics.widthPixels-dp(16)).coerceAtLeast(dp(220))
        captionParams=params(captionWidth,WindowManager.LayoutParams.WRAP_CONTENT,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)
        try{wm.addView(caption,captionParams);wm.addView(ball,ballParams)}catch(e:Exception){logger.error("创建悬浮窗口失败",e);runCatching{if(caption.isAttachedToWindow)wm.removeView(caption)};isRunning=false;stopSelf();return}
        applyCaptionVisibility(false);attachGestures();RecognitionController.addListener(this)
    }
    private fun params(w:Int,h:Int,flags:Int)=WindowManager.LayoutParams(w,h,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,flags,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.START}
    private fun attachGestures(){
        var downX=0f;var downY=0f;var startX=0;var startY=0;var moved=false;var longPressed=false
        val closeAction={RecognitionController.cancel();Toast.makeText(this,"悬浮小球已关闭。",Toast.LENGTH_SHORT).show();stopSelf();true}
        ball.setOnClickListener{RecognitionController.toggle()};ball.setOnLongClickListener{closeAction()}
        var pending:Runnable?=null
        ball.setOnTouchListener{_,event->
            when(event.action){
                MotionEvent.ACTION_DOWN->{downX=event.rawX;downY=event.rawY;startX=ballParams.x;startY=ballParams.y;moved=false;longPressed=false;pending=Runnable{if(!moved){longPressed=true;ball.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS);ball.performLongClick()}}.also{handler.postDelayed(it,700)};true}
                MotionEvent.ACTION_MOVE->{val x=(event.rawX-downX).toInt();val y=(event.rawY-downY).toInt();if(kotlin.math.abs(x)+kotlin.math.abs(y)>dp(6)){moved=true;pending?.let(handler::removeCallbacks)};if(!longPressed){ballParams.x=startX+x;ballParams.y=startY+y;safeUpdate(ball,ballParams);moveCaption()};true}
                MotionEvent.ACTION_UP->{pending?.let(handler::removeCallbacks);if(!moved&&!longPressed)ball.performClick();true}
                MotionEvent.ACTION_CANCEL->{pending?.let(handler::removeCallbacks);true}
                else->false
            }
        }
    }
    private fun moveCaption(){val screenWidth=resources.displayMetrics.widthPixels;captionParams.x=(ballParams.x-captionParams.width+dp(58)).coerceIn(dp(8),(screenWidth-captionParams.width-dp(8)).coerceAtLeast(dp(8)));captionParams.y=(ballParams.y-dp(94)).coerceAtLeast(dp(8));safeUpdate(caption,captionParams)}
    private fun applyCaptionVisibility(show:Boolean){caption.visibility=if(show)View.VISIBLE else View.GONE;captionParams.flags=WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or (if(show)0 else WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE);safeUpdate(caption,captionParams);if(show)moveCaption()}
    private fun safeUpdate(view:View,params:WindowManager.LayoutParams){if(!view.isAttachedToWindow)return;try{wm.updateViewLayout(view,params)}catch(e:Exception){logger.error("更新悬浮窗口失败",e);stopSelf()}}
    override fun onRecognitionState(listening:Boolean,status:String,text:String){handler.post{if(listening&&!previousListening)manuallyHidden=false;previousListening=listening;this.listening=listening;ball.update(listening,level);captionText.text=text.ifBlank{status};applyCaptionVisibility(!manuallyHidden&&(listening||text.isNotBlank()))}}
    override fun onAudioLevel(level:Float){handler.post{this.level=level;ball.update(listening,level)}}
    private fun notifyForeground(){(getSystemService(NOTIFICATION_SERVICE)as NotificationManager).createNotificationChannel(NotificationChannel(CHANNEL,"悬浮语音输入",NotificationManager.IMPORTANCE_LOW));val intent=Intent(this,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP);val open=PendingIntent.getActivity(this,0,intent,PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT);startForeground(7,Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.app_icon).setContentTitle("悬浮语音输入正在运行").setContentText("点击开始或停止，长按关闭悬浮球").setContentIntent(open).build())}
    private fun dp(value:Int)=(value*resources.displayMetrics.density).toInt()
    override fun onBind(intent:Intent?)=null
    override fun onDestroy(){handler.removeCallbacksAndMessages(null);RecognitionController.removeListener(this);if(::ball.isInitialized)runCatching{if(ball.isAttachedToWindow)wm.removeView(ball)};if(::caption.isInitialized)runCatching{if(caption.isAttachedToWindow)wm.removeView(caption)};isRunning=false;super.onDestroy()}
}
