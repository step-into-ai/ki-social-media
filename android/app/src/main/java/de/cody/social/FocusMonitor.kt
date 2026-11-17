package de.cody.social

import android.app.*
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.*
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.*
import android.provider.Settings
import android.view.*
import android.widget.*
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import java.util.Calendar

data class FocusApp(val pkg:String,val name:String)
object FocusStore {
    val apps=listOf(FocusApp("com.google.android.youtube","YouTube"),FocusApp("com.zhiliaoapp.musically","TikTok"),FocusApp("com.instagram.android","Instagram"))
    fun prefs(c:Context)=c.getSharedPreferences("cody-focus",Context.MODE_PRIVATE)
    fun enabled(c:Context)=prefs(c).getBoolean("enabled",false)
    fun monitored(c:Context,p:String)=prefs(c).getBoolean("watch:$p",true)
    fun opens(c:Context,p:String)=prefs(c).getInt("opens:$p",5)
    fun minutes(c:Context,p:String)=prefs(c).getInt("minutes:$p",10)
    fun usageAllowed(c:Context):Boolean {
        val a=c.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        return a.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,android.os.Process.myUid(),c.packageName)==AppOpsManager.MODE_ALLOWED
    }
    fun ready(c:Context)=usageAllowed(c)&&Settings.canDrawOverlays(c)
    fun start(c:Context) {if(enabled(c)&&ready(c))runCatching {c.startForegroundService(Intent(c,FocusMonitor::class.java))}}
    fun startOfDay(now:Long)=Calendar.getInstance().apply {timeInMillis=now;set(Calendar.HOUR_OF_DAY,0);set(Calendar.MINUTE,0);set(Calendar.SECOND,0);set(Calendar.MILLISECOND,0)}.timeInMillis
    fun events(c:Context,from:Long,until:Long):List<FocusEvent> {
        val result=mutableListOf<FocusEvent>()
        val stream=(c.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager).queryEvents(from,until)
        val e=UsageEvents.Event()
        while(stream.hasNextEvent()) {stream.getNextEvent(e);when(e.eventType) {
            UsageEvents.Event.ACTIVITY_RESUMED->result.add(FocusEvent(e.packageName,e.timeStamp,true))
            UsageEvents.Event.SCREEN_NON_INTERACTIVE,UsageEvents.Event.KEYGUARD_SHOWN,UsageEvents.Event.DEVICE_SHUTDOWN->result.add(FocusEvent(null,e.timeStamp,false))
        }}
        return result
    }
    val ignored=setOf("com.android.systemui","com.samsung.android.honeyboard","com.google.android.inputmethod.latin")
    fun snapshot(c:Context,now:Long):FocusDay {
        if(!usageAllowed(c))return FocusDay(emptyMap(),emptyMap(),null)
        val day=startOfDay(now)
        return FocusPolicy.summarize(events(c,day-86_400_000L,now),day,now,ignored)
    }
}

class FocusMonitor:Service() {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Default)
    private var overlay:View?=null
    private var previous:String?=null
    private var day=0L
    private var captured=0L
    private var lastRedirect=0L
    private var snapshot=FocusDay(emptyMap(),emptyMap(),null)
    override fun onBind(intent:Intent?):IBinder?=null
    override fun onCreate() {
        super.onCreate()
        val manager=getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("cody-focus","KI Social Media App-Limits",NotificationManager.IMPORTANCE_LOW))
        val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java).putExtra("focus_settings",true),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop=PendingIntent.getService(this,1,Intent(this,FocusMonitor::class.java).setAction("stop"),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        startForeground(303,NotificationCompat.Builder(this,"cody-focus").setSmallIcon(android.R.drawable.ic_lock_lock).setContentTitle("KI Social Media App-Limits aktiv").setContentText("YouTube, TikTok und Instagram nach deinen Tageslimits").setContentIntent(open).addAction(0,"Ausschalten",stop).setOngoing(true).build())
        scope.launch {while(isActive) {runCatching {check()};delay(1200)}}
    }
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        if(intent?.action=="stop") {FocusStore.prefs(this).edit().putBoolean("enabled",false).apply();stopSelf();return START_NOT_STICKY}
        return START_STICKY
    }
    private suspend fun check() {
        if(!FocusStore.enabled(this)||!FocusStore.ready(this)){stopSelf();return}
        val now=System.currentTimeMillis()
        val power=getSystemService(PowerManager::class.java);val keyguard=getSystemService(KeyguardManager::class.java)
        val updates=FocusStore.events(this,now-4000,now)
        var foreground=previous
        updates.forEach {e->if(!e.resumed)foreground=null else if(e.pkg !in FocusStore.ignored)foreground=e.pkg}
        if(!power.isInteractive||keyguard.isKeyguardLocked)foreground=null
        if(captured==0L||now-captured>=15000||foreground!=previous||day!=FocusStore.startOfDay(now)) {
            snapshot=FocusStore.snapshot(this,now);captured=now;day=FocusStore.startOfDay(now)
            if(foreground==null && power.isInteractive&&!keyguard.isKeyguardLocked)foreground=snapshot.active
            val editor=FocusStore.prefs(this).edit().putLong("heartbeat",now).putLong("usage_day",day)
            FocusStore.apps.forEach {a->editor.putInt("used_opens:${a.pkg}",snapshot.openings[a.pkg]?:0).putLong("used_ms:${a.pkg}",snapshot.milliseconds[a.pkg]?:0)}
            editor.apply()
        }
        previous=foreground
        val app=FocusStore.apps.find {it.pkg==foreground}
        if(app==null){withContext(Dispatchers.Main){removeOverlay()};return}
        if(!FocusStore.monitored(this,app.pkg))return
        val used=(snapshot.milliseconds[app.pkg]?:0)+(if(snapshot.active==app.pkg)now-captured else 0)
        if(FocusPolicy.exceeded(snapshot.openings[app.pkg]?:0,used,FocusStore.opens(this,app.pkg),FocusStore.minutes(this,app.pkg))) {
            if(now-lastRedirect<3000)return
            lastRedirect=now
            withContext(Dispatchers.Main) {
                showOverlay(app)
                runCatching {startActivity(destination(app))}
            }
        } else withContext(Dispatchers.Main){removeOverlay()}
    }
    private fun destination(app:FocusApp)=Intent(this,MainActivity::class.java).putExtra("focus_redirect",app.name).putExtra("focus_short",app.name!="YouTube").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
    private fun showOverlay(app:FocusApp) {
        if(overlay!=null)return
        val paper=getSharedPreferences("cody-social",MODE_PRIVATE).getString("theme_mode","graphit")=="papier"
        val ink=if(paper)Color.rgb(32,34,30) else Color.rgb(243,241,233)
        val accent=if(paper)Color.rgb(88,103,70) else Color.rgb(227,174,103)
        val panel=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;gravity=Gravity.CENTER;setPadding(40,40,40,40);setBackgroundColor(if(paper)Color.rgb(244,241,234) else Color.rgb(24,24,23))}
        panel.addView(TextView(this).apply {text="${app.name}: Tageslimit erreicht";textSize=25f;setTextColor(ink);gravity=Gravity.CENTER})
        panel.addView(TextView(this).apply {text="Deine ausgewählten Inhalte warten in KI Social Media.";textSize=17f;setTextColor(if(paper)Color.rgb(101,104,94) else Color.rgb(181,179,170));setPadding(0,25,0,25)})
        panel.addView(Button(this).apply {text="KI Social Media öffnen";setTextColor(if(paper)Color.WHITE else Color.rgb(40,32,20));background=android.graphics.drawable.GradientDrawable().apply {setColor(accent);cornerRadius=12*resources.displayMetrics.density};setOnClickListener {startActivity(destination(app));removeOverlay()}})
        val params=WindowManager.LayoutParams(-1,-1,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT)
        (getSystemService(WINDOW_SERVICE) as WindowManager).addView(panel,params);overlay=panel
    }
    private fun removeOverlay(){overlay?.let {runCatching {(getSystemService(WINDOW_SERVICE) as WindowManager).removeView(it)}};overlay=null}
    override fun onDestroy(){scope.cancel();removeOverlay();FocusStore.prefs(this).edit().putLong("heartbeat",0).apply();super.onDestroy()}
}

class FocusBootReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent?) {if(intent?.action==Intent.ACTION_BOOT_COMPLETED)FocusStore.start(context)}
}
