param([switch]$DebugOnly)
$ErrorActionPreference='Stop'
if(-not $env:JAVA_HOME){throw 'Set JAVA_HOME to JDK 17 or later.'}
if(-not $env:ANDROID_HOME){throw 'Set ANDROID_HOME to your Android SDK.'}
$project=$PSScriptRoot
Push-Location -LiteralPath $project
try {
    if($DebugOnly){$tasks=@(':app:testDebugUnitTest',':app:assembleDebug',':app:lintDebug')}
    else {$tasks=@(':app:testReleaseUnitTest',':app:assembleRelease',':app:lintRelease')}
    & .\gradlew.bat @tasks --console=plain
    if($LASTEXITCODE -ne 0){throw 'Android build failed.'}
    if(-not $DebugOnly){
        $out=Join-Path (Split-Path -Parent $project) 'dist'
        New-Item -ItemType Directory -Path $out -Force | Out-Null
        $apk=Join-Path $out 'KI-Social-Media-0.1.0-beta.1.apk'
        Copy-Item -LiteralPath 'app\build\outputs\apk\release\app-release.apk' -Destination $apk -Force
        & "$env:ANDROID_HOME\build-tools\36.0.0\apksigner.bat" verify --verbose $apk
        if($LASTEXITCODE -ne 0){throw 'APK signature verification failed.'}
        [IO.File]::WriteAllText((Join-Path $out 'SHA256SUMS'),(Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()+"  KI-Social-Media-0.1.0-beta.1.apk`n")
        Write-Output "Ready: $apk"
    }
} finally {Pop-Location}
