package de.cody.social

data class FocusEvent(val pkg:String?,val at:Long,val resumed:Boolean)
data class FocusDay(val milliseconds:Map<String,Long>,val openings:Map<String,Int>,val active:String?)

object FocusPolicy {
    fun summarize(events:List<FocusEvent>,start:Long,end:Long,ignored:Set<String>):FocusDay {
        val totals=mutableMapOf<String,Long>();val launches=mutableMapOf<String,Int>()
        var active:String?=null;var since=start
        fun close(at:Long) {active?.let {p->val duration=minOf(at,end)-maxOf(since,start);if(duration>0)totals[p]=(totals[p]?:0)+duration};active=null}
        events.sortedBy {it.at}.forEach {e->
            if(e.at<=end) {
                if(!e.resumed)close(e.at)
                else if(e.pkg!=null && e.pkg !in ignored && e.pkg!=active) {
                    close(e.at);active=e.pkg;since=e.at
                    if(e.at>=start)launches[e.pkg]=(launches[e.pkg]?:0)+1
                }
            }
        }
        val current=active;close(end)
        return FocusDay(totals,launches,current)
    }
    fun exceeded(openings:Int,milliseconds:Long,maxOpenings:Int,maxMinutes:Int)=
        openings>maxOpenings || milliseconds>=maxMinutes*60_000L
}
