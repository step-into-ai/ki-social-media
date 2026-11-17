package de.cody.social

import org.junit.Assert.*
import org.junit.Test

class FocusPolicyTest {
    @Test fun firstFiveOpeningsAreAllowedAndSixthRedirects() {
        assertFalse(FocusPolicy.exceeded(5,1_000,5,10))
        assertTrue(FocusPolicy.exceeded(6,1_000,5,10))
    }
    @Test fun tenMinutesAreATotalDailyBudget() {
        assertFalse(FocusPolicy.exceeded(2,599_999,5,10))
        assertTrue(FocusPolicy.exceeded(2,600_000,5,10))
    }
    @Test fun activitiesAndNotificationShadeDoNotInventNewOpenings() {
        val day=FocusPolicy.summarize(listOf(FocusEvent("youtube",0,true),FocusEvent("youtube",1000,true),FocusEvent("systemui",2000,true),FocusEvent("youtube",3000,true),FocusEvent("launcher",4000,true)),0,5000,setOf("systemui"))
        assertEquals(1,day.openings["youtube"])
        assertEquals(4000L,day.milliseconds["youtube"])
    }
    @Test fun screenLockStopsTimeAndNextOpeningCountsAgain() {
        val day=FocusPolicy.summarize(listOf(FocusEvent("youtube",0,true),FocusEvent(null,3000,false),FocusEvent("youtube",7000,true)),0,8000,emptySet())
        assertEquals(2,day.openings["youtube"])
        assertEquals(4000L,day.milliseconds["youtube"])
    }
    @Test fun midnightClipsTimeAndKeepsPerAppCountersSeparate() {
        val day=FocusPolicy.summarize(listOf(FocusEvent("youtube",9000,true),FocusEvent("tiktok",13000,true)),10000,15000,emptySet())
        assertEquals(3000L,day.milliseconds["youtube"])
        assertNull(day.openings["youtube"])
        assertEquals(1,day.openings["tiktok"])
        assertEquals(2000L,day.milliseconds["tiktok"])
    }
}
