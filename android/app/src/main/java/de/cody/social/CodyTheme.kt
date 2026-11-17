package de.cody.social

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Graphit = darkColorScheme(
    primary=Color(0xFFE3AE67), onPrimary=Color(0xFF282014),
    primaryContainer=Color(0xFF483821), onPrimaryContainer=Color(0xFFF6DDB9),
    secondary=Color(0xFFE3AE67), onSecondary=Color(0xFF282014),
    secondaryContainer=Color(0xFF393329), onSecondaryContainer=Color(0xFFF3F1E9),
    tertiary=Color(0xFFB5C497), onTertiary=Color(0xFF202519),
    background=Color(0xFF181817), onBackground=Color(0xFFF3F1E9),
    surface=Color(0xFF232321), onSurface=Color(0xFFF3F1E9),
    surfaceVariant=Color(0xFF2B2B27), onSurfaceVariant=Color(0xFFB5B3AA),
    outline=Color(0xFF85847B), outlineVariant=Color(0xFF3D3C37),
    error=Color(0xFFFFB4AB), onError=Color(0xFF690005),
    surfaceTint=Color.Transparent
)

private val Papier = lightColorScheme(
    primary=Color(0xFF586746), onPrimary=Color.White,
    primaryContainer=Color(0xFFE2E8D5), onPrimaryContainer=Color(0xFF26331C),
    secondary=Color(0xFF586746), onSecondary=Color.White,
    secondaryContainer=Color(0xFFE5E9DC), onSecondaryContainer=Color(0xFF26331C),
    tertiary=Color(0xFF657356), onTertiary=Color.White,
    background=Color(0xFFF4F1EA), onBackground=Color(0xFF20221E),
    surface=Color(0xFFFCFAF5), onSurface=Color(0xFF20221E),
    surfaceVariant=Color(0xFFE9E7DE), onSurfaceVariant=Color(0xFF65685E),
    outline=Color(0xFF77796F), outlineVariant=Color(0xFFD9DBCF),
    error=Color(0xFFA52A24), onError=Color.White,
    surfaceTint=Color.Transparent
)

@Composable fun CodyTheme(paper:Boolean,content:@Composable ()->Unit) {
    MaterialTheme(
        colorScheme=if(paper)Papier else Graphit,
        typography=Typography(
            bodyLarge=TextStyle(fontFamily=FontFamily.SansSerif,fontSize=16.sp,lineHeight=24.sp),
            bodyMedium=TextStyle(fontFamily=FontFamily.SansSerif,fontSize=14.sp,lineHeight=20.sp),
            titleLarge=TextStyle(fontFamily=FontFamily.SansSerif,fontSize=22.sp,lineHeight=28.sp,fontWeight=FontWeight.SemiBold),
            titleMedium=TextStyle(fontFamily=FontFamily.SansSerif,fontSize=18.sp,lineHeight=24.sp,fontWeight=FontWeight.SemiBold)
        ),
        shapes=Shapes(small=RoundedCornerShape(8.dp),medium=RoundedCornerShape(12.dp),large=RoundedCornerShape(16.dp)),
        content=content
    )
}
