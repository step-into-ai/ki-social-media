import java.util.Properties
plugins { id("com.android.application"); id("org.jetbrains.kotlin.plugin.compose") }
val signingValues=Properties().apply { rootProject.file(".signing/signing.properties").takeIf { it.exists() }?.inputStream()?.use(::load) }
android {
    namespace="de.cody.social"
    compileSdk { version=release(36) { minorApiLevel=1 } }
    defaultConfig {
        applicationId="de.stepintoai.kisocial"; minSdk=29; targetSdk=36
        versionCode=1; versionName="0.1.0-beta.1"
        testInstrumentationRunner="androidx.test.runner.AndroidJUnitRunner"
    }
    signingConfigs {
        create("release") {
            storeFile=rootProject.file(".signing/ki-social-media.p12")
            storePassword=signingValues.getProperty("storePassword","")
            keyAlias="ki-social-media"; keyPassword=signingValues.getProperty("keyPassword","")
            storeType="PKCS12"
        }
    }
    buildTypes { release { isMinifyEnabled=false; signingConfig=signingConfigs.getByName("release") } }
    compileOptions { sourceCompatibility=JavaVersion.VERSION_17; targetCompatibility=JavaVersion.VERSION_17 }
    buildFeatures { compose=true; buildConfig=true }
    testBuildType="release"
    lint { abortOnError=true }
}
dependencies {
    testImplementation("junit:junit:4.13.2")
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.core:core-ktx:1.18.0")
    implementation("androidx.webkit:webkit:1.16.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation(platform("androidx.compose:compose-bom:2024.09.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
}
