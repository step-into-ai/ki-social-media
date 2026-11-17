package de.cody.social

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.delay

@Composable fun FocusControls(activity:ComponentActivity,revision:Int,onChanged:()->Unit) {
    val prefs=FocusStore.prefs(activity)
    val enabled=remember(revision){FocusStore.enabled(activity)}
    val usage=FocusStore.usageAllowed(activity)
    val overlay=Settings.canDrawOverlays(activity)
    var editing by remember {mutableStateOf<FocusApp?>(null)}
    LaunchedEffect(Unit){while(true){delay(5000);onChanged()}}
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment=Alignment.CenterVertically) {
            Text("Aktiv",fontSize=17.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f))
            Switch(enabled,{on->
                prefs.edit().putBoolean("enabled",on).apply()
                if(on){
                    if(ContextCompat.checkSelfPermission(activity,Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)ActivityCompat.requestPermissions(activity,arrayOf(Manifest.permission.POST_NOTIFICATIONS),303)
                    FocusStore.start(activity)
                }else activity.stopService(Intent(activity,FocusMonitor::class.java))
                onChanged()
            })
        }
        HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
        Text("Tägliche Limits",fontSize=18.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.padding(top=8.dp))
        FocusStore.apps.forEach {app->
            val monitored=remember(revision){FocusStore.monitored(activity,app.pkg)}
            val today=prefs.getLong("usage_day",0)==FocusStore.startOfDay(System.currentTimeMillis())
            val count=if(today)prefs.getInt("used_opens:${app.pkg}",0) else 0
            val elapsed=if(today)prefs.getLong("used_ms:${app.pkg}",0) else 0
            Row(Modifier.fillMaxWidth().clickable{editing=app}.padding(vertical=7.dp),verticalAlignment=Alignment.CenterVertically){
                Icon(if(app.name=="YouTube")Icons.Default.PlayCircle else if(app.name=="Instagram")Icons.Default.CameraAlt else Icons.Default.MusicNote,null,modifier=Modifier.size(25.dp))
                Column(Modifier.weight(1f).padding(start=13.dp)){
                    Text(app.name,fontSize=16.sp,fontWeight=FontWeight.SemiBold)
                    Text("${FocusStore.opens(activity,app.pkg)} Öffnungen · ${FocusStore.minutes(activity,app.pkg)} Min.",fontSize=13.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(if(monitored)"Heute: $count Öffnungen · ${elapsed/60_000} Min." else "Limit pausiert",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(Icons.Default.ChevronRight,"Limit für ${app.name} bearbeiten")
            }
            HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
        }
        Text("Limits gelten für jede App einzeln.",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Android-Zugriffe",fontSize=18.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.padding(top=14.dp))
        listOf("Nutzungszugriff" to usage,"Über anderen Apps" to overlay).forEachIndexed {i,(label,allowed)->
            Row(Modifier.fillMaxWidth().clickable{
                if(i==0)activity.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                else activity.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:"+activity.packageName)))
            }.padding(vertical=10.dp),verticalAlignment=Alignment.CenterVertically){
                Icon(if(allowed)Icons.Default.CheckCircle else Icons.Default.Info,null,tint=if(allowed)MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.error)
                Text(label,modifier=Modifier.weight(1f).padding(start=10.dp),fontSize=14.sp)
                Text(if(allowed)"Erlaubt" else "Einrichten",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
    editing?.let {app->
        var opens by remember(app.pkg){mutableStateOf(FocusStore.opens(activity,app.pkg).toString())}
        var minutes by remember(app.pkg){mutableStateOf(FocusStore.minutes(activity,app.pkg).toString())}
        var watched by remember(app.pkg){mutableStateOf(FocusStore.monitored(activity,app.pkg))}
        val valid=opens.toIntOrNull() in 1..100 && minutes.toIntOrNull() in 1..240
        AlertDialog(onDismissRequest={editing=null},title={Text(app.name)},text={Column(verticalArrangement=Arrangement.spacedBy(12.dp)){
            Row(verticalAlignment=Alignment.CenterVertically){Text("Limit anwenden",modifier=Modifier.weight(1f));Switch(watched,{watched=it})}
            OutlinedTextField(opens,{v->if(v.length<=3&&v.all(Char::isDigit))opens=v},label={Text("Öffnungen / Tag")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),singleLine=true)
            OutlinedTextField(minutes,{v->if(v.length<=3&&v.all(Char::isDigit))minutes=v},label={Text("Minuten / Tag")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),singleLine=true)
        }},confirmButton={TextButton(enabled=valid,onClick={prefs.edit().putInt("opens:${app.pkg}",opens.toInt()).putInt("minutes:${app.pkg}",minutes.toInt()).putBoolean("watch:${app.pkg}",watched).apply();editing=null;onChanged()}){Text("Speichern")}},dismissButton={TextButton(onClick={editing=null}){Text("Abbrechen")}})
    }
}
