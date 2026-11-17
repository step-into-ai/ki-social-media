# Android selbst bauen

Die offizielle APK ist fertig signiert auf GitHub Releases verfügbar. Für einen
eigenen Build: JDK 17+, Android SDK Platform 36 mit Minor API 1, Build Tools 36.0.0.
Der Gradle-Wrapper lädt Gradle 9.3.1 mit festgelegtem SHA-256; AGP ist 9.1.1.

Setze `JAVA_HOME` und `ANDROID_HOME` auf deine eigenen Installationen. Keine
benutzerspezifischen Verzeichnisse sind im Projekt fest eingetragen.

## Tests ohne Release-Schlüssel

```bash
cd android
chmod +x gradlew
./gradlew :app:testReleaseUnitTest :app:assembleDebug :app:lintDebug
```

Windows: `android/Build.ps1 -DebugOnly` aus dem Projektverzeichnis.
Die Unit-Tests sind im Projekt für die Release-Variante angelegt; dafür wird kein
signiertes Release-Paket und kein privater Release-Schlüssel benötigt.

## Eigener signierter Release

```bash
python3 tools/create_signing.py
cd android
./gradlew :app:testReleaseUnitTest :app:assembleRelease :app:lintRelease
```

Windows: nach dem Python-Aufruf `android/Build.ps1`. Das Skript legt die APK und
SHA256SUMS unter `dist` ab und prüft die Signatur mit `apksigner`.
Unter Linux liegt das APK-Ergebnis unter `android/app/build/outputs/apk/release`.

`tools/create_signing.py` erzeugt einmalig einen eigenen Schlüssel und verweigert
das Ersetzen eines vorhandenen. `.signing` bleibt privat und muss für spätere
Updates sicher aufbewahrt werden. Der öffentliche Build verwendet eine andere
Paketkennung und eine andere Signatur als die ursprüngliche private App.

Bei Veröffentlichung eines eigenen Forks `applicationId`, App-Name und Deep-Link-
Schema ändern, damit dein Fork neben dem Original installiert werden kann. Der
interne Kotlin-Namespace `de.cody.social` ist kein Konto und keine Serverbindung.

Der offizielle Build enthält weder eine Standard-Serveradresse noch API- oder
Plattformschlüssel. Kopplung erfolgt erst beim ersten Start über HTTPS.

Öffentlicher SHA-256-Fingerabdruck des offiziellen Signierzertifikats:

```text
cc82ecddf31fbfc7040c2b64342747254736d4bef44548759eda0e95b52e04e0
```

Release-Dateien enthalten `SHA256SUMS` und `RELEASE-INFO.json`. Der Fingerabdruck
bezeichnet das öffentliche Zertifikat; der private Schlüssel wird nicht ausgeliefert.
