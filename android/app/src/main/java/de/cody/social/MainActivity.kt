package de.cody.social

import android.annotation.SuppressLint
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.outlined.*
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.semantics.Role
import android.content.Intent
import android.content.Context
import android.content.pm.ActivityInfo
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.SurfaceView
import android.view.TextureView
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.Button
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.TimeUnit
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val Navy:Color @Composable get()=MaterialTheme.colorScheme.background
private val Panel:Color @Composable get()=MaterialTheme.colorScheme.surface
private val Cyan:Color @Composable get()=MaterialTheme.colorScheme.primary
private val Muted:Color @Composable get()=MaterialTheme.colorScheme.onSurfaceVariant
private const val DEFAULT_SERVER=""
private val DiscoveryYellow=Color(0xFFE5B943)
private fun Modifier.discoveryFrame(enabled:Boolean,radius:Int=12):Modifier=if(enabled)border(2.dp,DiscoveryYellow,RoundedCornerShape(radius.dp)) else this
private val http=OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS).readTimeout(30,TimeUnit.SECONDS).build()
private fun JSONObject.str(key:String)=optString(key,"").takeUnless { it=="null" } ?: ""
private data class Video(val id:String,val externalId:String,val platform:String,val format:String,val title:String,val creator:String,val thumbnail:String,val url:String,val duration:String,val seen:Boolean,val favorite:Boolean,val sourceId:Int,val discovered:Boolean=false,val suggestionId:String="")
private data class Creator(val id:Int,val title:String,val handle:String,val platform:String,val mode:String,val enabled:Boolean,val status:String,val message:String,val count:Int,val delivery:String="videos",val checkedAt:String="",val successAt:String="")
private data class Post(val id:String,val sourceId:Int,val creator:String,val handle:String,val author:String,val text:String,val translated:String,val translationState:String,val url:String,val published:String,val media:List<String>,val seen:Boolean,val favorite:Boolean,val kind:String="x",val basis:String="",val title:String="",val dateKnown:Boolean=true,val videoId:String="",val discovered:Boolean=false,val suggestionId:String="")
private fun posts(a:JSONArray)=List(a.length()) { i->a.getJSONObject(i).let { p->Post(p.str("id"),p.optInt("source_id"),p.str("creator"),p.str("handle"),p.str("author"),p.str("text"),p.str("text_de"),p.str("translation_status"),p.str("url"),p.str("published_at"),p.optJSONArray("media")?.let { m->List(m.length()){m.getString(it)}.filter{it.isNotBlank()} } ?: emptyList(),p.optInt("seen")==1,p.optInt("favorite")==1,p.str("kind").ifBlank{"x"},p.str("basis"),p.str("title"),p.optInt("date_known",1)!=0,p.str("video_id"),p.optBoolean("is_discovery",false),p.str("suggestion_id")) } }
private fun postDate(value:String)=try { OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("dd.MM.yyyy · HH:mm",Locale.GERMAN)) } catch(_:Exception) {value.take(16)}
private fun platformName(value:String)=when(value){"youtube"->"YouTube";"tiktok"->"TikTok";"x"->"X";"rss"->"RSS / Atom";else->value}
private fun videos(a:JSONArray)=List(a.length()) { i->a.getJSONObject(i).let { Video(it.str("id"),it.str("external_id"),it.str("platform"),it.str("format"),it.str("title"),it.str("creator"),it.str("thumbnail"),it.str("url"),it.str("duration"),it.optInt("seen")==1,it.optInt("favorite")==1,it.optInt("source_id"),it.optBoolean("is_discovery",false),it.str("suggestion_id")) } }
private fun creators(a:JSONArray)=List(a.length()) { i->a.getJSONObject(i).let { Creator(it.getInt("id"),it.str("title"),it.str("handle"),it.str("platform"),it.str("mode"),it.optInt("enabled")==1,it.str("status"),it.str("message"),it.optInt(if(it.str("platform") in listOf("x","rss"))"post_count" else "video_count"),it.str("delivery").ifBlank{"videos"},it.str("checked_at"),it.str("success_at")) } }

private class ApiFailure(val status:Int,message:String):IllegalStateException(message)
private class Api(val base:String,val token:String) {
    init { val u=Uri.parse(base);require(u.scheme=="https" && u.host!=null && u.userInfo==null) { "Bitte eine HTTPS-Adresse verwenden." } }
    fun optional(path:String):JSONObject?=try {request(path)} catch(e:ApiFailure){if(e.status==404)null else throw e}
    fun request(path:String,body:JSONObject?=null,auth:Boolean=true):JSONObject {
        val builder=Request.Builder().url(base.trimEnd('/')+path)
        if(auth)builder.header("Authorization","Bearer $token")
        if(body!=null)builder.post(body.toString().toRequestBody("application/json".toMediaType()))
        http.newCall(builder.build()).execute().use { response->
            val raw=response.body?.string() ?: "{}"
            val data=try { JSONObject(raw) } catch(_:Exception) { JSONObject() }
            if(!response.isSuccessful)throw ApiFailure(response.code,data.optString("error","Server nicht erreichbar (${response.code})."))
            return data
        }
    }
}

class MainActivity:ComponentActivity() {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main)
    private val prefs by lazy { getSharedPreferences("cody-social",MODE_PRIVATE) }
    private var token by mutableStateOf("")
    private var server by mutableStateOf(DEFAULT_SERVER)
    private var page by mutableIntStateOf(0)
    private var longs by mutableStateOf<List<Video>>(emptyList())
    private var shorts by mutableStateOf<List<Video>>(emptyList())
    private var news by mutableStateOf<List<Post>>(emptyList())
    private var newsCreator by mutableIntStateOf(0)
    private var sources by mutableStateOf<List<Creator>>(emptyList())
    private var loading by mutableStateOf(false)
    private var message by mutableStateOf("")
    private var shortPosition by mutableIntStateOf(0)
    private var shortVideoId by mutableStateOf("")
    private var shortCreator by mutableIntStateOf(0)
    private var shortControls by mutableStateOf(true)
    private var player by mutableStateOf<Video?>(null)
    private var sharedLink by mutableStateOf("")
    private var fullView:View?=null
    private var fullCallback:WebChromeClient.CustomViewCallback?=null
    private var previousOrientation=ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
    private var activeWeb:WebView?=null
    private var loadJob:Job?=null
    private var autoJob:Job?=null
    private var seenSyncJob:Job?=null
    private var seenIds by mutableStateOf<Set<String>>(emptySet())
    private val seenQueueLock=Any()
    private var focusRevision by mutableIntStateOf(0)
    private var themeMode by mutableStateOf("graphit")
    private var settingsPage by mutableStateOf("")
    private var extensionReady by mutableStateOf(false)
    private var discoveryState by mutableStateOf(JSONObject())
    private var backendCapabilities by mutableStateOf(JSONObject())
    private var suggestionItems by mutableStateOf<List<JSONObject>>(emptyList())
    private var summaryItems by mutableStateOf<List<JSONObject>>(emptyList())
    private var requestError by mutableStateOf("")
    private fun setTheme(value:String){themeMode=value;prefs.edit().putString("theme_mode",value).apply()}


    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        token=prefs.getString("token","") ?: "";server=prefs.getString("server",DEFAULT_SERVER) ?: DEFAULT_SERVER
        if(prefs.getInt("feed_cache_version",0)<3)prefs.edit().remove("long").remove("short").remove("posts").putInt("feed_cache_version",3).apply()
        themeMode=prefs.getString("theme_mode","graphit") ?: "graphit"
        seenIds=prefs.getStringSet("seen_ids",emptySet())?.toSet() ?: emptySet()
        try { longs=videos(JSONArray(prefs.getString("long","[]")));shorts=videos(JSONArray(prefs.getString("short","[]")));sources=creators(JSONArray(prefs.getString("sources","[]")));news=posts(JSONArray(prefs.getString("posts","[]"))) } catch(_:Exception) { }
        setContent { CodyTheme(themeMode=="papier") {App()} }
        receive(intent)
        if(token.isNotEmpty())load()
    }
    override fun onNewIntent(intent:Intent) { super.onNewIntent(intent);setIntent(intent);receive(intent) }
    override fun onResume() {
        super.onResume();activeWeb?.onResume();focusRevision++;FocusStore.start(this)
        if(token.isNotEmpty())load()
        autoJob?.cancel();autoJob=scope.launch {while(isActive){delay(30_000);if(token.isNotEmpty())load()}}
    }
    override fun onPause() { autoJob?.cancel();activeWeb?.evaluateJavascript("if(window.codyPause)codyPause();",null);activeWeb?.onPause();super.onPause() }
    override fun onDestroy() { loadJob?.cancel();scope.cancel();super.onDestroy() }
    private fun receive(intent:Intent) {
        if(intent.getBooleanExtra("focus_settings",false)){page=3;settingsPage="focus"}
        intent.getStringExtra("focus_redirect")?.let {name->player=null;page=if(intent.getBooleanExtra("focus_short",false))1 else 0;message="$name: Tageslimit erreicht. Hier ist deine eigene Auswahl."}
        val uri=intent.data
        if(uri?.scheme=="kisocial" && uri.host=="pair") {
            val base=uri.getQueryParameter("server") ?: DEFAULT_SERVER
            val code=uri.getQueryParameter("code") ?: ""
            if(code.isNotEmpty())pair(base,code)
        }
        if(intent.action==Intent.ACTION_SEND) {
            val text=intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
            sharedLink=Regex("https://[^\\s<>]+").find(text)?.value ?: text;page=3
        }
    }
    private fun pair(base:String,code:String) {
        scope.launch {
            loading=true
            try {
                val result=withContext(Dispatchers.IO) { Api(base,"").request("/api/pair",JSONObject().put("code",code),false) }
                token=result.getString("token");server=base.trimEnd('/')
                prefs.edit().putString("token",token).putString("server",server).apply()
                message="Mit deinem Server verbunden.";load()
            } catch(e:Exception) { message=e.message ?: "Verbindung fehlgeschlagen." } finally { loading=false }
        }
    }
    private fun load(poll:Boolean=false) {
        if(token.isEmpty() || loadJob?.isActive==true)return
        loadJob=scope.launch {
            loading=true
            try {
                var again=true;var attempts=0
                while(again && attempts++<40) {
                    val data=withContext(Dispatchers.IO) {
                        val api=Api(server,token);syncSeen(api)
                        val sourceData=api.request("/api/sources")
                        val longData=api.request("/api/feed?format=long")
                        val shortData=api.request("/api/feed?format=short")
                        val combined=api.optional("/api/news")
                        val postData=combined ?: api.request("/api/posts")
                        val extras=JSONObject().put("available",combined!=null)
                        if(combined!=null) {
                            runCatching{api.optional("/api/capabilities")}.getOrNull()?.let{extras.put("capabilities",it)}
                            runCatching{api.optional("/api/discovery")}.getOrNull()?.let{extras.put("discovery",it)}
                            runCatching{api.optional("/api/suggestions")}.getOrNull()?.let{extras.put("suggestions",it.optJSONArray("suggestions"))}
                            runCatching{api.optional("/api/summaries")}.getOrNull()?.let{extras.put("summaries",it.optJSONArray("summaries"))}
                        }
                        listOf(sourceData,longData,shortData,postData,extras)
                    }
                    requestError=""
                    extensionReady=data[4].optBoolean("available")
                    data[4].optJSONObject("discovery")?.let{discoveryState=it}
                    data[4].optJSONObject("capabilities")?.let{backendCapabilities=it}
                    data[4].optJSONArray("suggestions")?.let{a->suggestionItems=List(a.length()){a.getJSONObject(it)}}
                    data[4].optJSONArray("summaries")?.let{a->summaryItems=List(a.length()){a.getJSONObject(it)}}
                    sources=creators(data[0].getJSONArray("sources"));longs=videos(data[1].getJSONArray("videos"));shorts=videos(data[2].getJSONArray("videos"));news=posts(data[3].getJSONArray("posts"))
                    if(shortPosition>=shorts.size)shortPosition=0
                    prefs.edit().putString("sources",data[0].getJSONArray("sources").toString()).putString("long",data[1].getJSONArray("videos").toString()).putString("short",data[2].getJSONArray("videos").toString()).putString("posts",data[3].getJSONArray("posts").toString()).apply()
                    again=data[0].optBoolean("refreshing")
                    message=if(again)"Cody prüft deine Creator …" else "${longs.size} Videos · ${shorts.size} Kurzvideos · ${news.size} Beiträge"
                    if(again)delay(2500)
                }
            } catch(e:CancellationException) { throw e }
            catch(e:Exception) {requestError=e.message ?: "Server nicht erreichbar.";message="Gespeicherte Auswahl bleibt verfügbar."}
            finally { loading=false }
        }
    }
    private fun mutate(path:String,body:JSONObject,reload:Boolean=true,onSuccess:(()->Unit)?=null,onResult:((JSONObject)->Unit)?=null) {
        scope.launch {
            try {requestError="";val result=withContext(Dispatchers.IO) {Api(server,token).request(path,body)};onResult?.invoke(result);onSuccess?.invoke();if(reload)load()}
            catch(e:Exception) {requestError=e.message ?: "Änderung fehlgeschlagen."}
        }
    }
    private fun refresh() { mutate("/api/refresh",JSONObject()) }
    private fun update(c:Creator,mode:String=c.mode,enabled:Boolean=c.enabled)=mutate("/api/source",JSONObject().put("id",c.id).put("mode",mode).put("enabled",enabled))
    private fun markSeen(v:Video) {
        if(v.id in seenIds)return
        seenIds=seenIds+v.id
        synchronized(seenQueueLock) {
            val pending=prefs.getStringSet("pending_seen",emptySet())?.toSet() ?: emptySet()
            prefs.edit().putStringSet("seen_ids",seenIds).putStringSet("pending_seen",pending+v.id).apply()
        }
        longs=longs.map { if(it.id==v.id)it.copy(seen=true) else it };shorts=shorts.map { if(it.id==v.id)it.copy(seen=true) else it }
        if(player?.id==v.id)player=player?.copy(seen=true)
        if(shortVideoId==v.id)shortVideoId=""
        pushSeen()
    }
    private suspend fun syncSeen(api:Api) {
        val pending=synchronized(seenQueueLock) {prefs.getStringSet("pending_seen",emptySet())?.toSet() ?: emptySet()}
        pending.toList().chunked(400).forEach {batch->
            api.request("/api/seen",JSONObject().put("ids",JSONArray(batch)))
            synchronized(seenQueueLock) {val current=prefs.getStringSet("pending_seen",emptySet())?.toSet() ?: emptySet();prefs.edit().putStringSet("pending_seen",current-batch.toSet()).apply()}
        }
    }
    private fun pushSeen() {
        if(seenSyncJob?.isActive==true)return
        seenSyncJob=scope.launch {var ok=false;try {withContext(Dispatchers.IO){syncSeen(Api(server,token))};ok=true}catch(_:Exception){}finally{seenSyncJob=null;if(ok&&!prefs.getStringSet("pending_seen",emptySet()).isNullOrEmpty())pushSeen()}}
    }
    private fun markPost(p:Post,favorite:Boolean?=null) {
        if(p.videoId.isNotBlank())(longs+shorts).find{it.id==p.videoId}?.let{markSeen(it)}
        val body=JSONObject().put("id",p.id).put("seen",true)
        if(favorite!=null)body.put("favorite",favorite)
        mutate("/api/post",body,p.discovered&&favorite==true,onResult={result->
            if(p.discovered)result.optJSONObject("subscribed_creator")?.let{creator->Toast.makeText(this@MainActivity,"${creator.str("title")} zur Quellenliste hinzugefügt",Toast.LENGTH_SHORT).show()}
        })
        news=news.map {if(it.id==p.id)it.copy(seen=true,favorite=favorite ?: it.favorite) else it}
    }
    private fun toggleFavorite(v:Video) {
        val favorite=!v.favorite
        mutate("/api/video",JSONObject().put("id",v.id).put("favorite",favorite),reload=v.discovered&&favorite,onResult={result->
            val creator=result.optJSONObject("subscribed_creator")
            fun updated(video:Video)=video.copy(favorite=favorite,discovered=if(creator!=null)false else video.discovered,sourceId=creator?.optInt("id") ?: video.sourceId)
            longs=longs.map{if(it.id==v.id)updated(it) else it};shorts=shorts.map{if(it.id==v.id)updated(it) else it}
            if(player?.id==v.id)player=updated(player!!)
            if(v.discovered&&creator!=null)Toast.makeText(this@MainActivity,"${creator.str("title")} zur Quellenliste hinzugefügt",Toast.LENGTH_SHORT).show()
        })
    }
    private fun blockCreator(sourceId:Int,suggestionId:String,name:String) {
        val body=JSONObject().put("blocked",true)
        if(suggestionId.isNotBlank())body.put("suggestion_id",suggestionId) else body.put("source_id",sourceId)
        mutate("/api/creator/block",body,onSuccess={
            fun matches(id:Int,suggestion:String)=(sourceId>0&&id==sourceId)||(suggestionId.isNotBlank()&&suggestion==suggestionId)
            longs=longs.filterNot{matches(it.sourceId,it.suggestionId)};shorts=shorts.filterNot{matches(it.sourceId,it.suggestionId)}
            news=news.filterNot{matches(it.sourceId,it.suggestionId)}
            player?.let{if(matches(it.sourceId,it.suggestionId))player=null}
            Toast.makeText(this@MainActivity,"$name wird nicht mehr angezeigt",Toast.LENGTH_SHORT).show()
        })
    }
    private fun closeFullscreen() {
        if(fullView==null && fullCallback==null)return
        (fullView as? ZoomFrame)?.resetZoom()
        fullView?.let { (it.parent as? ViewGroup)?.removeView(it) };fullView=null
        val callback=fullCallback;fullCallback=null;callback?.onCustomViewHidden()
        requestedOrientation=previousOrientation
        val bars=WindowCompat.getInsetsController(window,window.decorView)
        if(page==1 && !shortControls)bars.hide(WindowInsetsCompat.Type.systemBars()) else bars.show(WindowInsetsCompat.Type.systemBars())
        Log.i("CodyFullscreen","closed")
    }

    private inner class ZoomFrame(context:Context,private val videoView:View):FrameLayout(context) {
        private var zoom=1f
        private var scaling=false
        private var downX=0f
        private var downY=0f
        private val controls=LinearLayout(context)
        private val hide=Runnable {controls.visibility=View.GONE}
        private fun videoSurface(view:View):View? {
            if(view is SurfaceView || view is TextureView)return view
            if(view is ViewGroup)for(i in 0 until view.childCount)videoSurface(view.getChildAt(i))?.let{return it}
            return null
        }
        private fun applyZoom(value:Float) {
            zoom=value.coerceIn(1f,3f)
            val target=videoSurface(videoView) ?: videoView
            target.pivotX=target.width/2f;target.pivotY=target.height/2f
            target.scaleX=zoom;target.scaleY=zoom
            Log.i("CodyFullscreen","zoom=$zoom target=${target.javaClass.simpleName}")
        }
        fun resetZoom(){applyZoom(1f)}
        private val scale=ScaleGestureDetector(context,object:ScaleGestureDetector.SimpleOnScaleGestureListener(){
            override fun onScale(detector:ScaleGestureDetector):Boolean {applyZoom(zoom*detector.scaleFactor);return true}
        })
        init {
            tag="cody-fullscreen"
            setBackgroundColor(android.graphics.Color.BLACK);keepScreenOn=true;clipChildren=true
            addView(videoView,LayoutParams(-1,-1))
            val fill=Button(context).apply {
                text="Füllen";contentDescription="Bild füllen oder anpassen"
                setOnClickListener {
                    val ratio=(this@ZoomFrame.width.toFloat()/this@ZoomFrame.height.coerceAtLeast(1))/(16f/9f)
                    applyZoom(if(zoom>1.01f)1f else maxOf(1f,ratio));reveal()
                }
            }
            val close=Button(context).apply {text="✕";contentDescription="Vollbild verlassen";setOnClickListener {closeFullscreen()}}
            controls.addView(fill);controls.addView(close)
            addView(controls,LayoutParams(-2,-2,android.view.Gravity.TOP or android.view.Gravity.END).apply {topMargin=12;rightMargin=16})
            reveal()
        }
        private fun reveal(){controls.visibility=View.VISIBLE;removeCallbacks(hide);postDelayed(hide,3500)}
        override fun dispatchTouchEvent(event:MotionEvent):Boolean {
            scale.onTouchEvent(event)
            if(event.actionMasked==MotionEvent.ACTION_DOWN){downX=event.x;downY=event.y}
            if(event.pointerCount>1 && !scaling) {
                scaling=true
                val cancel=MotionEvent.obtain(event);cancel.action=MotionEvent.ACTION_CANCEL;super.dispatchTouchEvent(cancel);cancel.recycle()
            }
            if(scaling) {
                if(event.actionMasked==MotionEvent.ACTION_UP || event.actionMasked==MotionEvent.ACTION_CANCEL)scaling=false
                return true
            }
            if(event.actionMasked==MotionEvent.ACTION_UP && kotlin.math.abs(event.x-downX)<25 && kotlin.math.abs(event.y-downY)<25)reveal()
            return super.dispatchTouchEvent(event)
        }
    }

    @Composable private fun Robot(size:Int=32) { Image(painterResource(R.drawable.cody_robot),"Cody",Modifier.size(size.dp).clip(CircleShape),contentScale=ContentScale.Crop) }
    @Composable private fun App() {
        BackHandler(enabled=player!=null || page!=0 || fullView!=null || settingsPage.isNotEmpty()) { when {fullView!=null->closeFullscreen();player!=null->player=null;settingsPage.isNotEmpty()->settingsPage="";else->page=0} }
        SideEffect {
            val bars=WindowCompat.getInsetsController(window,window.decorView)
            bars.isAppearanceLightStatusBars=themeMode=="papier" && page!=1
            bars.isAppearanceLightNavigationBars=themeMode=="papier" && page!=1
            @Suppress("DEPRECATION")
            window.statusBarColor=if(page==1)android.graphics.Color.BLACK else if(themeMode=="papier")0xFFF4F1EA.toInt() else 0xFF181817.toInt()
            @Suppress("DEPRECATION")
            window.navigationBarColor=window.statusBarColor
        }
        if(token.isEmpty()) {PairScreen();return}
        LaunchedEffect(page,shortControls) {
            if(fullView==null) {
                val bars=WindowCompat.getInsetsController(window,window.decorView)
                bars.systemBarsBehavior=WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                if(page==1 && !shortControls)bars.hide(WindowInsetsCompat.Type.systemBars()) else bars.show(WindowInsetsCompat.Type.systemBars())
            }
        }
        Scaffold(containerColor=Navy,bottomBar={
            AnimatedVisibility(visible=page!=1 || shortControls,enter=fadeIn()+expandVertically(),exit=fadeOut()+shrinkVertically()) {
                if(page==1)CodyTheme(false){BottomNavigation()} else BottomNavigation()
            }
        }) {padding->
            Column(Modifier.fillMaxSize().padding(padding)) {
                if(page!=1)Row(Modifier.fillMaxWidth().height(60.dp).padding(horizontal=20.dp),verticalAlignment=Alignment.CenterVertically) {
                    if(player!=null || settingsPage.isNotEmpty())IconButton(onClick={if(player!=null)player=null else settingsPage=""},modifier=Modifier.size(48.dp)){Icon(Icons.AutoMirrored.Filled.ArrowBack,"Zurück")}
                    if(page==0){Robot();Spacer(Modifier.width(10.dp))}
                    Text(when {settingsPage=="focus"->"Mission Self Control";settingsPage=="discover"->"Entdecker";page==2->"News";page==3->"Einstellungen";else->"Cody"},fontSize=if(settingsPage=="focus")20.sp else 24.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f))
                    if(settingsPage.isEmpty())IconButton(onClick={refresh()},enabled=!loading) {if(loading)CircularProgressIndicator(Modifier.size(20.dp),strokeWidth=2.dp) else Icon(Icons.Default.Refresh,"Aktualisieren")}
                }
                if(requestError.isNotEmpty())Text(requestError,Modifier.padding(horizontal=20.dp,vertical=4.dp),fontSize=12.sp,color=MaterialTheme.colorScheme.error)
                when {player!=null->LongPlayer(player!!);page==0->Home();page==1->CodyTheme(false){Shorts()};page==2->News();else->Settings()}
            }
        }
    }
    @Composable private fun BottomNavigation() {
        Column(Modifier.background(Navy)) {
            HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
            Row(Modifier.fillMaxWidth().navigationBarsPadding().height(68.dp)) {
                val labels=listOf("Home","Short-Form","News","Einstellungen")
                val icons=listOf(Icons.Outlined.Home,Icons.Outlined.PlayCircleOutline,Icons.Outlined.Newspaper,Icons.Outlined.Settings)
                labels.forEachIndexed {i,label->
                    val selected=page==i
                    Column(Modifier.weight(1f).fillMaxHeight().selectable(selected=selected,role=Role.Tab,onClick={player=null;settingsPage="";page=i;if(i==1)shortControls=true}).testTag("nav-$i").padding(top=9.dp),horizontalAlignment=Alignment.CenterHorizontally) {
                        Icon(icons[i],label,tint=if(selected)Cyan else Muted,modifier=Modifier.size(24.dp))
                        Text(label,fontSize=10.sp,color=if(selected)MaterialTheme.colorScheme.onBackground else Muted,modifier=Modifier.padding(top=3.dp))
                        Spacer(Modifier.height(5.dp));Box(Modifier.width(26.dp).height(3.dp).clip(CircleShape).background(if(selected)Cyan else Color.Transparent))
                    }
                }
            }
        }
    }
    @Composable private fun Home() {
        val list=longs.filterNot {it.seen || it.id in seenIds}
        LazyColumn(contentPadding=PaddingValues(horizontal=20.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
            items(list,key={it.id}) {v->VideoCard(v)}
            if(list.isEmpty())item {Empty("Für jetzt bist du durch.","Neue Videos erscheinen automatisch.")}
            else item {Text("Ende deiner Auswahl",Modifier.fillMaxWidth().padding(vertical=12.dp),color=Muted,fontSize=12.sp)}
        }
    }
    @Composable private fun Duration(v:Video,modifier:Modifier=Modifier) {
        if(v.duration.isNotEmpty())Text(v.duration,modifier.background(Color.Black.copy(alpha=.85f),RoundedCornerShape(5.dp)).padding(horizontal=7.dp,vertical=3.dp),color=Color.White,fontSize=12.sp)
    }
    @Composable private fun Avatar(name:String,modifier:Modifier=Modifier) {
        Box(modifier.size(32.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant),contentAlignment=Alignment.Center) {Text(name.trim().take(1).uppercase(),fontSize=13.sp,fontWeight=FontWeight.SemiBold,color=Muted)}
    }
    @Composable private fun VideoCard(v:Video) {
        Column(Modifier.fillMaxWidth()) {
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).discoveryFrame(v.discovered).clickable{player=v}.testTag("video-${v.id}")) {
                Thumb(v.thumbnail,Modifier.fillMaxWidth().aspectRatio(16f/9f));Duration(v,Modifier.align(Alignment.BottomEnd).padding(8.dp))
            }
            Row(Modifier.padding(top=10.dp),verticalAlignment=Alignment.Top) {
                Column(Modifier.weight(1f).clickable{player=v}) {
                    Text(v.title,fontSize=19.sp,lineHeight=25.sp,fontWeight=FontWeight.SemiBold,maxLines=2,overflow=TextOverflow.Ellipsis)
                    Row(Modifier.padding(top=7.dp),verticalAlignment=Alignment.CenterVertically) {Avatar(v.creator,Modifier.size(24.dp));Text(v.creator,color=Muted,fontSize=13.sp,modifier=Modifier.padding(start=7.dp))}
                }
                IconButton(onClick={markSeen(v)},modifier=Modifier.size(48.dp)) {Icon(Icons.Outlined.CheckCircleOutline,"Als gesehen markieren")}
                VideoOptions(v)
            }
            HorizontalDivider(Modifier.padding(top=16.dp),color=MaterialTheme.colorScheme.outlineVariant)
        }
    }
    @Composable private fun LongPlayer(v:Video) {
        Column(Modifier.fillMaxSize()) {
            Player(v,Modifier.fillMaxWidth().aspectRatio(16f/9f).discoveryFrame(v.discovered,0).padding(if(v.discovered)2.dp else 0.dp),onSwipe={})
            val recommendations=longs.filterNot {it.seen || it.id in seenIds || it.id==v.id}.take(3)
            LazyColumn(Modifier.weight(1f),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
                item {
                    Text(v.title,fontSize=21.sp,lineHeight=28.sp,fontWeight=FontWeight.SemiBold)
                    Row(Modifier.fillMaxWidth().padding(top=10.dp),verticalAlignment=Alignment.CenterVertically){Avatar(v.creator);Text(v.creator,color=Muted,fontSize=13.sp,modifier=Modifier.weight(1f).padding(start=8.dp));VideoOptions(v)}
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick={markSeen(v)}) {Icon(Icons.Outlined.CheckCircleOutline,null,Modifier.size(18.dp));Text(if(v.seen||v.id in seenIds)" Gesehen" else " Als gesehen markieren",fontSize=12.sp)}
                        TextButton(onClick={toggleFavorite(v)}){Icon(if(v.favorite)Icons.Default.Bookmark else Icons.Outlined.BookmarkBorder,null,Modifier.size(18.dp));Text(if(v.discovered)" Merken + Creator" else " Merken",fontSize=12.sp)}
                    }
                    HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
                }
                if(recommendations.isNotEmpty())item {Text("Weitere Videos",fontSize=17.sp,fontWeight=FontWeight.SemiBold)}
                items(recommendations,key={it.id}) {next->Row(Modifier.fillMaxWidth().clickable{player=next},verticalAlignment=Alignment.CenterVertically) {
                    Box(Modifier.width(132.dp).clip(RoundedCornerShape(8.dp)).discoveryFrame(next.discovered,8)){Thumb(next.thumbnail,Modifier.fillMaxWidth().aspectRatio(16f/9f));Duration(next,Modifier.align(Alignment.BottomEnd).padding(3.dp))}
                    Column(Modifier.weight(1f).padding(start=12.dp)){Text(next.title,fontSize=14.sp,lineHeight=19.sp,fontWeight=FontWeight.SemiBold,maxLines=2,overflow=TextOverflow.Ellipsis);Text(next.creator,fontSize=12.sp,color=Muted,modifier=Modifier.padding(top=4.dp))}
                }}
                if(recommendations.isEmpty())item {Text("Ende deiner Auswahl",color=Muted,fontSize=13.sp)}
            }
        }
    }
    @Composable private fun CompactFilter(label:String,selected:Boolean,onClick:()->Unit) {
        FilterChip(selected=selected,onClick=onClick,label={Text(label,fontSize=13.sp,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.widthIn(max=165.dp))},border=null,shape=RoundedCornerShape(8.dp),colors=FilterChipDefaults.filterChipColors(containerColor=Color.Transparent,selectedContainerColor=MaterialTheme.colorScheme.primaryContainer,selectedLabelColor=MaterialTheme.colorScheme.onPrimaryContainer))
    }
    @Composable private fun VideoOptions(v:Video) {
        var open by remember(v.id){mutableStateOf(false)}
        Box {
            IconButton(onClick={open=true},modifier=Modifier.size(48.dp).testTag("video-options-${v.id}")){Icon(Icons.Default.MoreHoriz,"Videooptionen")}
            DropdownMenu(expanded=open,onDismissRequest={open=false}) {
                DropdownMenuItem(text={Text("Creator nicht mehr anzeigen")},onClick={open=false;blockCreator(v.sourceId,v.suggestionId,v.creator)})
            }
        }
    }
    @Composable private fun Shorts() {
        var interaction by remember {mutableIntStateOf(0)}
        val selectable=sources.filter {it.enabled && it.platform in listOf("youtube","tiktok") && it.mode!="long"}
        val selected=shortCreator.takeIf {id->selectable.any {it.id==id}} ?: 0
        val list=shorts.filter {!it.seen && it.id !in seenIds && (selected==0 || it.sourceId==selected)}
        val found=list.indexOfFirst {it.id==shortVideoId}
        val pos=if(found>=0)found else shortPosition.coerceIn(0,(list.size-1).coerceAtLeast(0))
        LaunchedEffect(shortControls,interaction,list.isEmpty()){if(list.isEmpty())shortControls=true else if(shortControls){delay(3500);shortControls=false}}
        Column(Modifier.fillMaxSize().background(Color.Black)) {
            AnimatedVisibility(visible=shortControls,enter=fadeIn()+expandVertically(),exit=fadeOut()+shrinkVertically()) {
                Row(Modifier.fillMaxWidth().height(56.dp).background(Navy),verticalAlignment=Alignment.CenterVertically) {
                    LazyRow(Modifier.weight(1f).testTag("creator-row"),contentPadding=PaddingValues(start=16.dp,end=8.dp),horizontalArrangement=Arrangement.spacedBy(4.dp)) {
                        item{CompactFilter("Alle",selected==0){shortCreator=0;shortPosition=0;shortVideoId="";shortControls=true;interaction++}}
                        items(selectable,key={it.id}){c->CompactFilter(c.title,selected==c.id){shortCreator=if(shortCreator==c.id)0 else c.id;shortPosition=0;shortVideoId="";shortControls=true;interaction++}}
                    }
                    Box(Modifier.width(1.dp).height(24.dp).background(MaterialTheme.colorScheme.outlineVariant))
                    list.getOrNull(pos)?.let {current->IconButton(onClick={toggleFavorite(current);interaction++},modifier=Modifier.size(48.dp).testTag("short-favorite")){
                        Icon(if(current.favorite)Icons.Default.Bookmark else Icons.Outlined.BookmarkBorder,if(current.discovered)"Merken und Creator hinzufügen" else "Merken")
                    }}
                    list.getOrNull(pos)?.let {VideoOptions(it)}
                    list.getOrNull(pos)?.let {current->TextButton(onClick={shortPosition=pos;markSeen(current);interaction++},modifier=Modifier.width(104.dp).height(48.dp).testTag("short-seen")){Icon(Icons.Outlined.CheckCircleOutline,null,Modifier.size(19.dp));Text(" Gesehen",fontSize=12.sp)}}
                }
            }
            if(list.isEmpty()){Empty("Für jetzt bist du durch.","Neue Kurzvideos erscheinen automatisch.");return@Column}
            val v=list[pos]
            LaunchedEffect(v.id){shortVideoId=v.id;shortPosition=pos}
            Box(Modifier.fillMaxWidth().weight(1f).discoveryFrame(v.discovered,0).padding(if(v.discovered)2.dp else 0.dp)){key(v.id){Player(v,Modifier.fillMaxSize(),onSwipe={delta->if(delta>0){shortPosition=pos;markSeen(v);shortControls=false}else if(pos>0){shortPosition=pos-1;shortVideoId=list[pos-1].id;shortControls=false}},onInteract={shortControls=!shortControls;interaction++})}}
        }
    }
    @Composable private fun News() {
        var onlyUnseen by remember {mutableStateOf(false)}
        val selectable=sources.filter{it.enabled && (it.platform in listOf("x","rss") || it.delivery!="videos")}
        val selected=newsCreator.takeIf{id->selectable.any{it.id==id}} ?: 0
        val list=news.filter{(selected==0 || it.sourceId==selected) && (!onlyUnseen || !it.seen)}
        LazyColumn(contentPadding=PaddingValues(horizontal=20.dp,vertical=4.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
            item{LazyRow(horizontalArrangement=Arrangement.spacedBy(5.dp)){item{CompactFilter("Alle",selected==0){newsCreator=0}};item{CompactFilter("Ungelesen",onlyUnseen){onlyUnseen=!onlyUnseen}};items(selectable,key={it.id}){c->CompactFilter(if(c.platform=="x")"@${c.handle}" else c.title,selected==c.id){newsCreator=if(selected==c.id)0 else c.id}}}}
            items(selectable.filter{(selected==0 || it.id==selected)&&it.status !in listOf("ok","")},key={"status:${it.id}"}){c->Text("${c.title}: "+if(c.status=="pending")"Wird abgerufen …" else c.message.ifBlank{"Abruf wird erneut versucht."},fontSize=12.sp,color=Muted)}
            items(list,key={it.id}){p->PostRow(p)}
            if(list.isEmpty())item{Empty(if(onlyUnseen)"Alles gelesen." else "Noch keine Beiträge.","Neue Beiträge deiner Quellen erscheinen hier.")}
        }
    }
    @Composable private fun PostRow(p:Post) {
        var menu by remember{mutableStateOf(false)}
        val clipboard=LocalClipboardManager.current
        Column(Modifier.fillMaxWidth().discoveryFrame(p.discovered).padding(if(p.discovered)12.dp else 0.dp).testTag(if(p.discovered)"discovery-post-${p.id}" else "post-${p.id}")) {
            Row(verticalAlignment=Alignment.CenterVertically) {
                Avatar(p.creator.ifBlank{p.author})
                Column(Modifier.weight(1f).padding(start=10.dp)){Text(p.creator.ifBlank{p.author},fontSize=15.sp,fontWeight=FontWeight.SemiBold);Text((if(p.kind=="x")"@${p.author} · " else if(!p.dateKnown)"Gefunden · " else "")+postDate(p.published),fontSize=11.sp,color=Muted)}
                Text(when(p.kind){"rss"->"RSS";"video_summary"->"Video";else->"X"},fontSize=12.sp,color=Muted)
            }
            if(!p.author.equals(p.handle,true)&&p.kind=="x")Text("In der Auswahl von @${p.handle}",fontSize=11.sp,color=Muted,modifier=Modifier.padding(top=5.dp))
            Text(when(p.kind){"rss"->p.basis.ifBlank{"RSS · Feed-Auszug möglich"};"video_summary"->p.basis.ifBlank{"Zusammenfassung · Transkript"};else->"Übersetzt"},fontSize=11.sp,color=Muted,modifier=Modifier.padding(top=10.dp,bottom=8.dp))
            if(p.kind!="x" && p.title.isNotBlank())Text(p.title,fontSize=18.sp,lineHeight=24.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.padding(bottom=8.dp))
            if(p.translated.isNotBlank() && p.translationState=="ready")SelectionContainer{Text(p.translated,fontSize=16.sp,lineHeight=24.sp)}
            else if(p.translationState=="original")SelectionContainer{Text(p.text,fontSize=16.sp,lineHeight=24.sp)}
            else Text(if(p.translationState=="error")"Übersetzung wird erneut versucht." else "Wird auf Deutsch übersetzt …",fontSize=14.sp,color=Muted)
            if(p.media.isNotEmpty())LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp),modifier=Modifier.padding(top=12.dp)){items(p.media){url->Thumb(url,Modifier.width(270.dp).height(190.dp).clip(RoundedCornerShape(12.dp)))}}
            Row(Modifier.fillMaxWidth().padding(top=7.dp),verticalAlignment=Alignment.CenterVertically) {
                TextButton(onClick={markPost(p)}){Icon(Icons.Default.Check,null,Modifier.size(18.dp));Text(if(p.seen)" Gelesen ✓" else " Gelesen",fontSize=12.sp)}
                TextButton(onClick={markPost(p,!p.favorite)}){Icon(if(p.favorite)Icons.Default.Bookmark else Icons.Outlined.BookmarkBorder,null,Modifier.size(18.dp));Text(if(p.discovered)" Merken + Creator" else " Merken",fontSize=12.sp)}
                Spacer(Modifier.weight(1f));Box{IconButton(onClick={menu=true}){Icon(Icons.Default.MoreHoriz,"Beitragsoptionen")};DropdownMenu(expanded=menu,onDismissRequest={menu=false}){
                    DropdownMenuItem(text={Text("Link kopieren")},onClick={clipboard.setText(AnnotatedString(p.url));menu=false},leadingIcon={Icon(Icons.Default.Link,null)})
                    if(p.discovered && p.suggestionId.isNotBlank()) {
                        DropdownMenuItem(text={Text("Creator abonnieren")},onClick={mutate("/api/suggestion",JSONObject().put("id",p.suggestionId).put("action","subscribe"));menu=false})
                        DropdownMenuItem(text={Text("Ausblenden")},onClick={mutate("/api/suggestion",JSONObject().put("id",p.suggestionId).put("action","dismiss"));menu=false})
                    }
                    DropdownMenuItem(text={Text("Creator nicht mehr anzeigen")},onClick={menu=false;blockCreator(p.sourceId,p.suggestionId,p.creator)})
                }}
            }
            HorizontalDivider(Modifier.padding(top=8.dp),color=MaterialTheme.colorScheme.outlineVariant)
        }
    }
    @Composable private fun Settings() {
        if(settingsPage=="focus"){LazyColumn(contentPadding=PaddingValues(20.dp)){item{FocusControls(this@MainActivity,focusRevision){focusRevision++}}};return}
        if(settingsPage=="discover"){DiscoverySettings();return}
        var editor by remember{mutableStateOf<Creator?>(null)}
        var add by remember(sharedLink){mutableStateOf(sharedLink.isNotBlank())}
        LazyColumn(contentPadding=PaddingValues(horizontal=20.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            item{Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){Text("Creator & Quellen",fontSize=18.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f));IconButton(onClick={add=true}){Icon(Icons.Default.Add,"Quelle hinzufügen")}}}
            items(sources,key={it.id}){c->
                Row(Modifier.fillMaxWidth().heightIn(min=72.dp),verticalAlignment=Alignment.CenterVertically){
                    Row(Modifier.weight(1f).clickable{editor=c}.padding(vertical=10.dp),verticalAlignment=Alignment.CenterVertically){Avatar(c.title);Column(Modifier.weight(1f).padding(start=10.dp)){Text(c.title,fontSize=14.sp,fontWeight=FontWeight.SemiBold,maxLines=1,overflow=TextOverflow.Ellipsis);Text(platformName(c.platform)+(if(c.platform=="youtube")" · "+modeName(c.mode) else "")+(if(c.delivery!="videos" && c.platform in listOf("youtube","tiktok"))" · "+deliveryName(c.delivery) else ""),fontSize=11.sp,color=Muted);if(c.status=="error")Text("Abruf prüfen",color=MaterialTheme.colorScheme.error,fontSize=11.sp)}}
                    Switch(checked=c.enabled,onCheckedChange={update(c,enabled=it)},modifier=Modifier.padding(start=4.dp));IconButton(onClick={editor=c},modifier=Modifier.size(48.dp)){Icon(Icons.Default.ChevronRight,"Quelle bearbeiten")}
                };HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
            }
            item{Spacer(Modifier.height(12.dp));SettingsLink("Mission Self Control",if(FocusStore.enabled(this@MainActivity))"Aktiv" else "Aus",focusSummary()){settingsPage="focus"}}
            item{SettingsLink("Entdecker","",if(suggestionItems.isNotEmpty())"${suggestionItems.size} neue Creator" else if(extensionReady)"Themen und neue Creator" else "Wird vorbereitet"){settingsPage="discover"}}
            item{Spacer(Modifier.height(12.dp));Text("Darstellung",fontSize=16.sp,fontWeight=FontWeight.SemiBold);Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){CompactFilter("Graphit",themeMode=="graphit"){setTheme("graphit")};CompactFilter("Papier",themeMode=="papier"){setTheme("papier")}}}
            item{HorizontalDivider(Modifier.padding(vertical=12.dp),color=MaterialTheme.colorScheme.outlineVariant);Row(verticalAlignment=Alignment.CenterVertically){Box(Modifier.size(7.dp).clip(CircleShape).background(MaterialTheme.colorScheme.tertiary));Text(if(loading)"Wird aktualisiert …" else if(requestError.isNotEmpty())"Offline" else "Verbunden",color=Muted,fontSize=12.sp,modifier=Modifier.weight(1f).padding(start=8.dp));TextButton(onClick={refresh()}){Text("Aktualisieren",fontSize=12.sp)}};Text("KI Social Media · "+BuildConfig.VERSION_NAME,color=Muted,fontSize=11.sp)}
        }
        if(add || editor!=null)SourceEditor(editor){add=false;editor=null;sharedLink=""}
    }
    private fun modeName(mode:String)=when(mode){"long"->"Lang";"short"->"Shorts";else->"Beides"}
    private fun deliveryName(value:String)=when(value){"news"->"Als News";"both"->"Beides";else->"Videos"}
    private fun focusSummary():String {val apps=FocusStore.apps.filter{FocusStore.monitored(this,it.pkg)};return if(apps.isEmpty())"Keine App ausgewählt" else if(apps.map{FocusStore.opens(this,it.pkg) to FocusStore.minutes(this,it.pkg)}.distinct().size==1)"${FocusStore.opens(this,apps.first().pkg)} Öffnungen · ${FocusStore.minutes(this,apps.first().pkg)} Min. je App / Tag" else "Individuelle Tageslimits"}
    @Composable private fun SettingsLink(title:String,status:String,detail:String,onClick:()->Unit){
        Column(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(vertical=15.dp)){Row(verticalAlignment=Alignment.CenterVertically){Text(title,fontSize=16.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f));if(status.isNotEmpty())Text(status,color=Cyan,fontSize=12.sp);Icon(Icons.Default.ChevronRight,null)};Text(detail,fontSize=12.sp,color=Muted,modifier=Modifier.padding(top=5.dp))};HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
    }
    @OptIn(ExperimentalMaterial3Api::class)
    @Composable private fun SourceEditor(c:Creator?,close:()->Unit) {
        var url by remember(c){mutableStateOf(sharedLink)}
        var mode by remember(c){mutableStateOf(c?.mode ?: "both")}
        var delivery by remember(c){mutableStateOf(c?.delivery ?: "videos")}
        var deleting by remember{mutableStateOf(false)}
        val detected=c?.platform ?: when{url.contains("youtu",true)->"youtube";url.contains("tiktok",true)->"tiktok";url.contains("x.com",true)||url.contains("twitter.com",true)->"x";url.isNotBlank()->"rss";else->""}
        val allowedDelivery=backendCapabilities.optJSONObject("delivery")?.optJSONArray(detected)?.let{a->List(a.length()){a.optString(it)}.toSet()} ?: if(detected=="tiktok")setOf("videos") else setOf("videos","news","both")
        ModalBottomSheet(onDismissRequest=close,containerColor=Panel) {
            Column(Modifier.fillMaxWidth().padding(horizontal=24.dp).verticalScroll(rememberScrollState()).imePadding().padding(bottom=28.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                Text(c?.title ?: "Quelle hinzufügen",fontSize=22.sp,fontWeight=FontWeight.SemiBold)
                if(c==null)OutlinedTextField(value=url,onValueChange={url=it},label={Text("Profil- oder Feed-Link")},singleLine=true,modifier=Modifier.fillMaxWidth())
                if(detected.isNotEmpty())Text(platformName(detected),fontSize=12.sp,color=Muted)
                if(detected=="youtube"){Text("Videoformat",fontSize=13.sp);FormatChoices(mode){mode=it}}
                if(detected in listOf("youtube","tiktok")){Text("Im Feed anzeigen",fontSize=13.sp);Row(horizontalArrangement=Arrangement.spacedBy(5.dp)){listOf("videos","news","both").forEach{value->FilterChip(selected=delivery==value,onClick={delivery=value},enabled=extensionReady && value in allowedDelivery,label={Text(deliveryName(value),fontSize=12.sp)})}};if(detected=="tiktok" && "news" !in allowedDelivery)Text("News benötigen ein verfügbares Transkript.",fontSize=12.sp,color=Muted);if(!extensionReady && delivery!="videos")Text("News-Zusammenfassungen werden gerade angebunden.",fontSize=12.sp,color=Muted)}
                if(c!=null){Text("${c.count} Einträge · "+when(c.status){"ok"->"aktuell";"pending"->"wird geladen";else->"Abruf prüfen"},fontSize=12.sp,color=Muted);if(c.message.isNotBlank())Text(c.message,fontSize=12.sp,color=Muted);if(c.successAt.isNotBlank())Text("Zuletzt erfolgreich: "+postDate(c.successAt),fontSize=11.sp,color=Muted)}
                Button(enabled=(c!=null || url.startsWith("https://"))&&(extensionReady||detected!="rss"),onClick={val body=JSONObject().put("mode",mode);if(detected=="rss")body.put("platform","rss");if(c!=null)body.put("id",c.id) else body.put("url",url.trim());if(extensionReady)body.put("delivery",delivery);mutate("/api/source",body,onSuccess=close)},modifier=Modifier.fillMaxWidth().height(48.dp)){Text(if(c==null)"Hinzufügen" else "Speichern")}
                if(detected=="rss" && !extensionReady)Text("RSS-Feeds werden gerade vorbereitet.",fontSize=12.sp,color=Muted)
                if(c!=null)TextButton(onClick={deleting=true}){Icon(Icons.Outlined.DeleteOutline,null);Text(" Quelle entfernen",color=MaterialTheme.colorScheme.error)}
            }
        }
        if(deleting && c!=null)AlertDialog(onDismissRequest={deleting=false},title={Text("Quelle entfernen?")},text={Text("${c.title} und die zugehörigen Einträge werden entfernt.")},confirmButton={TextButton(onClick={mutate("/api/source",JSONObject().put("id",c.id).put("delete",true),onSuccess=close)}){Text("Entfernen")}},dismissButton={TextButton(onClick={deleting=false}){Text("Abbrechen")}})
    }
    @Composable private fun DiscoveryPanel() {
        val config=discoveryState.optJSONObject("settings") ?: JSONObject()
        var enabled by remember(config.toString()){mutableStateOf(config.optBoolean("enabled",true))}
        var topics by remember(config.toString()){mutableStateOf(config.optJSONArray("topics")?.let{a->List(a.length()){a.optString(it)}.joinToString(", ")} ?: "KI, Automatisierung, praktische KI-Werkzeuge")}
        var exclude by remember(config.toString()){mutableStateOf(config.optJSONArray("exclude")?.let{a->List(a.length()){a.optString(it)}.joinToString(", ")} ?: "")}
        var platforms by remember(config.toString()){mutableStateOf(config.optJSONArray("platforms")?.let{a->List(a.length()){a.optString(it)}.toSet()} ?: setOf("youtube","x","tiktok"))}
        var frequency by remember(config.toString()){mutableIntStateOf(config.optInt("runs_per_day",2))}
        var maximum by remember(config.toString()){mutableIntStateOf(config.optInt("max_suggestions",3))}
        var saved by remember{mutableStateOf(false)}
        fun terms(value:String)=value.split(',', '\n').map{it.trim()}.filter{it.isNotBlank()}.distinct()
        val valid=terms(topics).isNotEmpty() && terms(topics).size<=12 && terms(exclude).size<=12 && (terms(topics)+terms(exclude)).all{it.length<=100} && platforms.isNotEmpty()
        LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            if(!extensionReady)item{Text("Wird vorbereitet",fontSize=13.sp,color=Muted)}
            item{Row(verticalAlignment=Alignment.CenterVertically){Text("Aktiv",fontSize=17.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f));Switch(enabled,{enabled=it;saved=false},enabled=extensionReady)}}
            item{OutlinedTextField(topics,{topics=it;saved=false},label={Text("Themen")},supportingText={Text("Mit Kommas trennen")},enabled=extensionReady,modifier=Modifier.fillMaxWidth())}
            item{OutlinedTextField(exclude,{exclude=it;saved=false},label={Text("Weniger davon")},enabled=extensionReady,modifier=Modifier.fillMaxWidth())}
            item{Text("Plattformen",fontSize=15.sp,fontWeight=FontWeight.SemiBold);Row(horizontalArrangement=Arrangement.spacedBy(5.dp)){listOf("youtube","x","tiktok").forEach{p->FilterChip(selected=p in platforms,onClick={if(extensionReady){platforms=if(p in platforms)platforms-p else platforms+p;saved=false}},enabled=extensionReady,label={Text(platformName(p),fontSize=12.sp)})}}}
            item{Text("Prüfungen pro Tag",fontSize=15.sp);Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf(1,2).forEach{n->FilterChip(selected=frequency==n,onClick={frequency=n;saved=false},enabled=extensionReady,label={Text("$n × täglich")})}}}
            item{Text("Vorschläge je Prüfung",fontSize=15.sp);Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){(1..3).forEach{n->FilterChip(selected=maximum==n,onClick={maximum=n;saved=false},enabled=extensionReady,label={Text(n.toString())})}}}
            item{Button(enabled=extensionReady&&valid,onClick={mutate("/api/discovery",JSONObject().put("enabled",enabled).put("topics",JSONArray(terms(topics))).put("exclude",JSONArray(terms(exclude))).put("platforms",JSONArray(platforms.sorted())).put("runs_per_day",frequency).put("max_suggestions",maximum),onSuccess={saved=true})},modifier=Modifier.fillMaxWidth()){Text(if(saved)"Gespeichert" else "Speichern")}}
            discoveryState.optJSONArray("runs")?.optJSONObject(0)?.let{run->item{
                HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
                Text("Letzte Prüfung",fontSize=15.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.padding(top=12.dp))
                Text(postDate(run.str("finished_at").ifBlank{run.str("started_at")}),fontSize=12.sp,color=Muted)
                if(run.str("message").isNotBlank())Text(run.str("message"),fontSize=12.sp,color=Muted)
                run.optJSONObject("platforms")?.let{states->states.keys().forEach{platform->val raw=states.opt(platform);val detail=if(raw is JSONObject)raw.str("message").ifBlank{raw.str("status")} else raw?.toString().orEmpty();if(detail.isNotBlank())Text(platformName(platform)+": "+detail,fontSize=12.sp,color=Muted)}}
            }}
            item{Text("Neue Creator",fontSize=18.sp,fontWeight=FontWeight.SemiBold)}
            if(suggestionItems.isEmpty())item{Text(if(extensionReady)"Noch keine neuen Vorschläge." else "Vorschläge erscheinen nach der Einrichtung.",fontSize=14.sp,color=Muted)}
            items(suggestionItems,key={it.str("id")}){s->
                Column(Modifier.fillMaxWidth().background(Panel,RoundedCornerShape(12.dp)).padding(15.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    Text(s.str("creator"),fontSize=16.sp,fontWeight=FontWeight.SemiBold)
                    Text(platformName(s.str("platform"))+" · "+postDate(s.str("published_at")),fontSize=11.sp,color=Muted)
                    Text(s.str("title"),fontSize=14.sp,fontWeight=FontWeight.SemiBold)
                    Text(s.str("reason"),fontSize=14.sp,lineHeight=21.sp)
                    val clipboard=LocalClipboardManager.current
                    TextButton(onClick={clipboard.setText(AnnotatedString(s.str("url")))}){Icon(Icons.Default.Link,null);Text(" Beitrag-Link kopieren")}
                    val profile=Uri.parse(s.str("profile_url"))
                    val canSubscribe=profile.scheme=="https" && profile.host!=null && !(s.str("platform")=="x" && profile.pathSegments.firstOrNull() in listOf("i","home","explore","search"))
                    Row(horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                        Button(enabled=canSubscribe,onClick={mutate("/api/suggestion",JSONObject().put("id",s.str("id")).put("action","subscribe"))}){Text("Abonnieren",fontSize=12.sp)}
                        TextButton(onClick={mutate("/api/suggestion",JSONObject().put("id",s.str("id")).put("action","dismiss"))}){Text("Ausblenden",fontSize=12.sp)}
                    }
                    TextButton(onClick={mutate("/api/suggestion",JSONObject().put("id",s.str("id")).put("action","mute"))}){Text("Creator stummschalten",fontSize=12.sp)}
                    if(!canSubscribe)Text("Creator-Profil wird noch geprüft.",fontSize=11.sp,color=Muted)
                    if(s.str("content_message").isNotBlank())Text(s.str("content_message"),fontSize=11.sp,color=Muted)
                }
            }
            discoveryState.optJSONArray("muted_creators")?.let{blocked->
                if(blocked.length()>0)item{HorizontalDivider();Text("Ausgeblendete Creator",fontSize=18.sp,fontWeight=FontWeight.SemiBold)}
                items(blocked.length(),key={"blocked:"+blocked.getJSONObject(it).str("platform")+":"+blocked.getJSONObject(it).str("handle")}){index->
                    val creator=blocked.getJSONObject(index)
                    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){
                        Column(Modifier.weight(1f)){Text(creator.str("title").ifBlank{creator.str("handle")},fontSize=14.sp);Text(platformName(creator.str("platform")),fontSize=12.sp,color=Muted)}
                        TextButton(onClick={mutate("/api/creator/block",JSONObject().put("platform",creator.str("platform")).put("handle",creator.str("handle")).put("blocked",false))}){Text("Wieder zulassen",fontSize=12.sp)}
                    }
                }
            }
        }
    }


    @Composable private fun DiscoverySettings() {DiscoveryPanel()}
    @Composable private fun FormatChoices(mode:String,onChange:(String)->Unit) {Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){listOf("long" to "Lang","short" to "Shorts","both" to "Beides").forEach{(v,l)->CompactFilter(l,mode==v){onChange(v)}}}}
    @Composable private fun PairScreen() {
        var base by remember{mutableStateOf(server)};var code by remember{mutableStateOf("")}
        Column(Modifier.fillMaxSize().background(Navy).statusBarsPadding().navigationBarsPadding().padding(28.dp),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally){
            Robot(80);Spacer(Modifier.height(20.dp));Text("KI Social Media",fontSize=26.sp,fontWeight=FontWeight.SemiBold);Spacer(Modifier.height(24.dp))
            OutlinedTextField(base,{base=it},label={Text("Serveradresse (HTTPS)")},modifier=Modifier.fillMaxWidth());OutlinedTextField(code,{code=it},label={Text("Verbindungscode")},modifier=Modifier.fillMaxWidth().padding(top=10.dp))
            Button(onClick={pair(base,code)},enabled=!loading&&code.isNotBlank()&&base.startsWith("https://"),modifier=Modifier.fillMaxWidth().padding(top=16.dp)){Text("Verbinden")};if(message.isNotEmpty())Text(message,color=Muted,fontSize=12.sp)
        }
    }
    @Composable private fun Empty(title:String,text:String) {Column(Modifier.fillMaxWidth().padding(vertical=48.dp,horizontal=24.dp),horizontalAlignment=Alignment.CenterHorizontally){Robot(56);Spacer(Modifier.height(18.dp));Text(title,fontSize=20.sp,fontWeight=FontWeight.SemiBold);Text(text,color=Muted,fontSize=14.sp,modifier=Modifier.padding(top=8.dp))}}
    @Composable private fun Thumb(url:String,modifier:Modifier) {
        val bitmap by produceState<ImageBitmap?>(null,url){value=withContext(Dispatchers.IO){try{val uri=Uri.parse(url);if(uri.scheme!="https")return@withContext null;http.newCall(Request.Builder().url(url).build()).execute().use{r->r.body?.byteStream()?.use{stream->val out=ByteArrayOutputStream();val buffer=ByteArray(8192);while(out.size()<3_000_000){val n=stream.read(buffer,0,minOf(buffer.size,3_000_000-out.size()));if(n<0)break;out.write(buffer,0,n)};val bytes=out.toByteArray();BitmapFactory.decodeByteArray(bytes,0,bytes.size,BitmapFactory.Options().apply{inSampleSize=2})?.asImageBitmap()}}}catch(_:Exception){null}}}
        Box(modifier.background(Panel),contentAlignment=Alignment.Center){if(bitmap!=null)Image(bitmap!!,null,Modifier.fillMaxSize(),contentScale=ContentScale.Crop) else Icon(Icons.Outlined.PlayCircleOutline,null,tint=Muted,modifier=Modifier.size(32.dp))}
    }


    @SuppressLint("SetJavaScriptEnabled","ClickableViewAccessibility")
    @Composable private fun Player(v:Video,modifier:Modifier,onSwipe:(Int)->Unit,onInteract:()->Unit={}) {
        var notice by remember(v.id) { mutableStateOf("") }
        val currentSwipe by rememberUpdatedState(onSwipe)
        val currentInteract by rememberUpdatedState(onInteract)
        Box(modifier.background(Color.Black)) {
            key(v.id) {
                AndroidView(modifier=Modifier.fillMaxSize(),factory={ context->
                    WebView(context).apply {
                        activeWeb=this
                        setBackgroundColor(android.graphics.Color.BLACK)
                        keepScreenOn=true
                        settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.mediaPlaybackRequiresUserGesture=false
                        settings.allowFileAccess=false;settings.allowContentAccess=false;settings.mixedContentMode=android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
                        settings.setSupportMultipleWindows(true);settings.javaScriptCanOpenWindowsAutomatically=false
                        if(WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT))WebViewCompat.addDocumentStartJavaScript(this,"""
                            (()=>{const apply=()=>{if(document.head&&!document.getElementById('cody-caption-preference')){const s=document.createElement('style');s.id='cody-caption-preference';s.textContent='.ytp-caption-window-container,.caption-window{display:none!important}';document.head.appendChild(s);}document.querySelectorAll('video').forEach(v=>{for(const track of v.textTracks)track.mode='disabled';});};new MutationObserver(apply).observe(document,{childList:true,subtree:true});apply();})();
                        """.trimIndent(),setOf("https://www.youtube.com"))
                        CookieManager.getInstance().setAcceptThirdPartyCookies(this,false)
                        webViewClient=object:WebViewClient() {
                            override fun shouldOverrideUrlLoading(view:WebView,request:WebResourceRequest):Boolean {
                                val u=request.url
                                val own=u.scheme=="https" && u.authority==Uri.parse(server).authority && u.path?.contains("/player/")==true
                                val embed=u.scheme=="https" && (u.host=="www.youtube.com" && u.path?.startsWith("/embed/")==true || u.host=="www.tiktok.com" && u.path?.startsWith("/player/v1/")==true)
                                val blocked=if(request.isForMainFrame)!own else request.hasGesture() && !embed
                                if(blocked)Log.i("CodyNavigation","blocked:"+(u.host ?: u.scheme))
                                return blocked
                            }
                        }
                        webChromeClient=object:WebChromeClient() {
                            override fun onCreateWindow(view:WebView,isDialog:Boolean,isUserGesture:Boolean,resultMsg:android.os.Message):Boolean {Log.i("CodyNavigation","blocked-new-window");return false}
                            override fun onShowCustomView(view:View,callback:CustomViewCallback) {
                                if(fullView!=null){callback.onCustomViewHidden();return}
                                val container=ZoomFrame(this@MainActivity,view)
                                fullView=container;fullCallback=callback
                                previousOrientation=requestedOrientation
                                if(v.format=="long")requestedOrientation=ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                                (window.decorView as ViewGroup).addView(container,FrameLayout.LayoutParams(-1,-1))
                                val bars=WindowCompat.getInsetsController(window,window.decorView)
                                bars.systemBarsBehavior=WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                                bars.hide(WindowInsetsCompat.Type.systemBars())
                                Log.i("CodyFullscreen","opened format="+v.format)
                            }
                            override fun onHideCustomView(){closeFullscreen()}
                        }
                        val origin=Uri.parse(server).let { "${it.scheme}://${it.authority}" }
                        if(WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER))WebViewCompat.addWebMessageListener(this,"CodyPlayback",setOf(origin)) { _,msg,sourceOrigin,isMainFrame,_->
                            if(!isMainFrame || sourceOrigin.toString().trimEnd('/')!=origin)return@addWebMessageListener
                            try {
                                val event=JSONObject(msg.data ?: "{}");val type=event.str("type")
                                Log.i("CodyPlayback",JSONObject().put("video",v.id).put("type",type).put("seconds",event.optDouble("seconds",0.0)).put("state",event.optInt("state",-9)).put("code",event.optInt("code",0)).toString())
                                val duration=event.optDouble("duration",0.0)
                                if(type=="time" && duration>0 && event.optDouble("seconds",0.0)>=duration*0.95)markSeen(v)
                                if(v.platform=="youtube" && type=="state" && event.optInt("state",-1)==0)markSeen(v)
                                if(type=="error")notice="Der Plattform-Player meldet ${event.optInt("code")}. Du kannst das Original öffnen."
                                if(type=="blocked")notice="Tippe im Player auf Wiedergabe."
                            }catch(_:Exception){}
                        }
                        if(v.format=="short") {
                            var startX=0f;var startY=0f
                            setOnTouchListener { _,event->
                                when(event.actionMasked) {
                                    MotionEvent.ACTION_DOWN->{startX=event.x;startY=event.y;false}
                                    MotionEvent.ACTION_UP->{
                                        val dy=event.y-startY;val dx=event.x-startX
                                        if(kotlin.math.abs(dy)>100*resources.displayMetrics.density && kotlin.math.abs(dy)>kotlin.math.abs(dx)*1.5) { currentSwipe(if(dy<0)1 else -1);true } else {currentInteract();false}
                                    }
                                    else->false
                                }
                            }
                        }
                        loadUrl(server.trimEnd('/')+"/player/${v.platform}/${v.externalId}")
                    }
                },onRelease={ web->if(activeWeb===web)activeWeb=null;web.stopLoading();web.loadUrl("about:blank");web.destroy() })
            }
            if(notice.isNotEmpty())Surface(color=Navy,modifier=Modifier.align(Alignment.BottomCenter).fillMaxWidth()) {Text(notice,fontSize=11.sp,color=Muted,modifier=Modifier.padding(8.dp))}
        }
    }
}
