# Daten und Verbindungen

- Quellen, Inhalte und Gesehen-/Merkenstatus liegen in der eigenen SQLite-Datenbank.
- Der Betreiber kontrolliert seinen Server und die dortigen Zugänge. Wer Zugriff
  auf `.env`, Datenvolume oder X-Sitzung hat, hat entsprechend privaten Zugriff.
- Die Android-App speichert ihre Kopplung im privaten App-Bereich. Cloud-Backup und
  Geräteübertragung dieser App-Daten sind deaktiviert. Keine Anbieter-Keys in der APK.
- YouTube-/TikTok-Einbettungen verbinden das Handy mit den Plattformen; dabei gelten
  deren Datenverarbeitungen. Das Backend ruft Metadaten und gewählte öffentliche Feeds ab.
- Bei eingeschaltetem Chat-Anbieter werden benötigte Texte/Transkripte an diesen
  Anbieter gesendet. Bei Cloud-Spracherkennung wird Audio an den gewählten Anbieter
  gesendet. Der Betreiber wählt Zugang, Modell und Ausgaben selbst.
- Die optionale lokale TikTok-Sprachprüfung nutzt eine Hörprobe von höchstens zwölf
  Sekunden. Audio und erkannter Text werden gelöscht; Sprache, Score und Prüfzeit
  können als Nachweis zwischengespeichert bleiben.
- X-Sitzungen bleiben im eigenen Datenvolume. Es gibt keine öffentliche Fernlogin-
  oder Browser-Debuggingroute. Keine Anmeldung wird mit dem Quellcode mitgeliefert.
- Mission Self Control braucht auf Wunsch Nutzungsdatenzugriff und Überlagerung für
  lokale App-Limits. Für Lesen und Videos sind diese Rechte nicht erforderlich.

Die App enthält keinen projektseitigen Analytics-Dienst und keine zentrale
Registrierung. Das ist keine Aussage über die eingebetteten Drittplattformen.
