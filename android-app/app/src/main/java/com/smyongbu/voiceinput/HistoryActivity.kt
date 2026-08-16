package com.smyongbu.voiceinput

import android.app.*
import android.content.*
import android.graphics.Color
import android.os.Bundle
import android.view.*
import android.widget.*
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

class HistoryActivity : Activity() {
    private lateinit var store:HistoryStore;private lateinit var list:ListView;private lateinit var count:TextView;private lateinit var adapter:HistoryAdapter
    override fun onCreate(state:Bundle?){super.onCreate(state);setContentView(R.layout.activity_history);applySystemInsets(findViewById(R.id.historyRoot));setupBottomNavigation(NAV_HISTORY);store=HistoryStore(this);list=findViewById(R.id.historyList);count=findViewById(R.id.historyCount);list.emptyView=findViewById(R.id.emptyText);adapter=HistoryAdapter();list.adapter=adapter;findViewById<Button>(R.id.clearButton).setOnClickListener{confirmClear()}}
    override fun onResume(){super.onResume();render()}
    override fun onDestroy(){store.close();super.onDestroy()}
    private fun render(){val items=store.list(500);count.text="${items.size} 条记录";adapter.items=items;adapter.notifyDataSetChanged()}
    private inner class HistoryAdapter:BaseAdapter(){var items:List<HistoryItem> = emptyList();override fun getCount()=items.size;override fun getItem(position:Int)=items[position];override fun getItemId(position:Int)=items[position].id
        override fun getView(position:Int,recycled:View?,parent:android.view.ViewGroup):View{val holder:Holder;val row:LinearLayout
            if(recycled==null){row=LinearLayout(this@HistoryActivity).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(16),dp(14),dp(16),dp(12));background=getDrawable(R.drawable.history_card)};val text=TextView(this@HistoryActivity).apply{textSize=17f;setTextColor(Color.rgb(15,23,42));setLineSpacing(0f,1.35f);setTextIsSelectable(true)};val meta=TextView(this@HistoryActivity).apply{textSize=12f;setTextColor(Color.rgb(71,85,105));setPadding(0,dp(10),0,dp(8))};val actions=LinearLayout(this@HistoryActivity).apply{orientation=LinearLayout.HORIZONTAL};val copy=actionButton("复制文字");val delete=actionButton("删除此条");actions.addView(copy,LinearLayout.LayoutParams(0,dp(48),1f).apply{marginEnd=dp(6)});actions.addView(delete,LinearLayout.LayoutParams(0,dp(48),1f).apply{marginStart=dp(6)});row.addView(text);row.addView(meta);row.addView(actions);holder=Holder(text,meta,copy,delete);row.tag=holder}
            else{row=recycled as LinearLayout;holder=row.tag as Holder}
            val item=getItem(position);holder.text.text=item.text;holder.meta.text="${localTime(item.createdAt)}　${engineName(item.engine)}";holder.copy.setOnClickListener{copy(item.text)};holder.delete.setOnClickListener{confirmDelete(item)};return row}
    }
    private data class Holder(val text:TextView,val meta:TextView,val copy:Button,val delete:Button)
    private fun actionButton(label:String)=Button(this).apply{text=label;isAllCaps=false;textSize=14f;setTextColor(Color.rgb(29,78,216));background=getDrawable(R.drawable.secondary_button)}
    private fun copy(text:String){(getSystemService(CLIPBOARD_SERVICE)as android.content.ClipboardManager).setPrimaryClip(ClipData.newPlainText("语音识别文字",text));Toast.makeText(this,"已复制到剪贴板。",Toast.LENGTH_SHORT).show()}
    private fun confirmDelete(item:HistoryItem){AlertDialog.Builder(this).setTitle("删除这条记录？").setMessage("删除后无法恢复。").setPositiveButton("确认删除"){_,_->store.delete(item.id);render()}.setNegativeButton("取消",null).show()}
    private fun confirmClear(){if(adapter.items.isEmpty()){Toast.makeText(this,"没有可以清空的记录。",Toast.LENGTH_SHORT).show();return};AlertDialog.Builder(this).setTitle("清空全部历史？").setMessage("所有识别历史将被永久删除。").setPositiveButton("确认清空"){_,_->store.clear();render()}.setNegativeButton("取消",null).show()}
    private fun engineName(engine:String)=when(engine){RecognitionController.ENGINE_DUAL->"实时＋校正";RecognitionController.ENGINE_ZIPFORMER->"Zipformer";RecognitionController.ENGINE_PARAFORMER->"Paraformer";RecognitionController.ENGINE_SYSTEM->"系统识别";else->"未知方式"}
    private fun localTime(raw:String)=try{LocalDateTime.parse(raw,DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss",Locale.ROOT)).atZone(ZoneOffset.UTC).withZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("yyyy年M月d日 HH:mm",Locale.SIMPLIFIED_CHINESE))}catch(_:Exception){raw}
    private fun dp(value:Int)=(value*resources.displayMetrics.density).toInt()
}
