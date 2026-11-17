# Optionale X-Anbindung

X verwendet Agent Reach 1.6.1 als optionale externe Bibliothek. Das ist eine
experimentelle Browseranbindung mit einer eigenen Sitzung pro Installation.
Es wird keine Sitzung des Autors mitgeliefert. X ist für YouTube, TikTok und RSS
nicht erforderlich. Plattformregeln, Kontrollen und Wartezeiten gelten weiterhin.

Die Containerinstallation enthält Python, Chromium und die Grundwerkzeuge.
Einmalig im eigenen Container die Twitter/X-Erweiterung vorbereiten:

```bash
docker compose exec backend agent-reach add twitter
```

Agent Reach lädt dafür seine eigenen gepinnten Browser-/Node-Werkzeuge nach
`data/reach`. Diese Daten bleiben privat. Der Browser hat keine öffentliche
Debugging-/VNC-Route. Docker setzt keinen Remote-Desktop auf.

Wenn du eine bereits im eigenen Browser angemeldete X-Sitzung ausdrücklich für
diesen eigenen Server verwenden möchtest:

1. Die beiden Werte `auth_token` und `ct0` persönlich in der normalen
   Entwickleransicht von `https://x.com` ablesen. Sie gewähren Sitzungszugriff.
2. Im vertrauten interaktiven SSH-Terminal auf deinem Server starten:

   ```bash
   docker compose exec backend python tools/connect_x.py
   ```

3. Die zwei Werte direkt in die maskierten Terminalfelder einfügen. Sie werden
   nicht als Kommandoargument, Zwischen-Datei oder Protokoll ausgegeben.
4. In der App das eigene gewünschte X-Profil hinzufügen und aktualisieren.
   Erst `ok` und echte aktuelle Beiträge belegen den erfolgreichen Abruf.

Keine Werte in Chat, Issues, Screenshots oder Git einfügen. Der Sitzungsspeicher
liegt ausschließlich im privaten eigenen Datenvolume. Bei einer persönlichen
Anmeldeprüfung oder Sperre anhalten und den Nutzer selbst prüfen lassen.

Für eine native Desktopinstallation ist auch der offizielle persönliche
`agent-reach login twitter`-Weg möglich. Den `HOME`-Ordner dabei bewusst auf
das eigene `data/reach` setzen, damit nicht versehentlich eine andere Sitzung
verwendet wird. Der headless Container bietet kein sichtbares Loginfenster.

Wenn die optionale Anmeldung fehlschlägt, funktionieren die anderen Quellen weiter.
Kein vollständiges Archiv, kein offizieller X-API-Zugang und keine dauerhafte
Zuverlässigkeit werden zugesagt.
