# Der Agent scrollt echte Feeds

Der optionale Browser-Entdecker öffnet gerenderte Plattformseiten in einem eigenen
Chromium-Profil. Er scrollt mit echten Mausradereignissen, liest die dadurch sichtbaren
Beitrags-/Videokarten und übergibt belegte Kandidaten an die konfigurierte KI-Auswahl.
Suchabruf und Browser-Fund sind in den Daten getrennt gekennzeichnet.

## Aktivieren

Voraussetzungen: aktuelle Repository-Fassung, aktivierter KI-Entdecker mit eigenen
Interessen, Chromium und Agent Reach. Im Compose-Image sind die Werkzeuge enthalten.

```bash
docker compose exec backend python tools/setup_browser.py
```

In der eigenen `.env` einstellen:

```dotenv
AI_ENABLED=true
CODY_BROWSER_DISCOVERY=true
CODY_BROWSER_PLATFORMS=youtube,x,tiktok
CODY_BROWSER_MAX_STEPS=6
CODY_BROWSER_MAX_SECONDS=60
CODY_BROWSER_FALLBACK_SEARCH=true
```

Gewählten KI-Anbieter wie in [PROVIDERS.md](PROVIDERS.md) konfigurieren, den Entdecker
in der App aktivieren und danach die eigene Instanz aktualisieren:

```bash
docker compose up -d
docker compose --profile ai up -d ai
```

Für X ist die eigene Sitzung gemäß [X.md](X.md) erforderlich. TikTok kann eine
persönliche Altersprüfung, Anmeldung oder Challenge verlangen. Diese führt der
Benutzer selbst im eigenen Browser aus. Sitzungen gehören ausschließlich dieser
Instanz. Die reguläre YouTube-/TikTok-Quellensammlung bleibt unabhängig davon nutzbar.

Die Browser-Erweiterung ist im aktuellen Repository-Quellstand enthalten; das bereits
veröffentlichte Backend-ZIP der Beta 0.1.0-beta.1 enthält sie noch nicht. Die vorhandene
APK bleibt mit den neuen Feed-Daten kompatibel.

## Ablauf und Grenzen

- **YouTube:** öffentlicher Hashtag-Feed zum aktuellen Interessengebiet.
- **X:** Startseiten-Timeline der eigenen angemeldeten Sitzung.
- **TikTok:** normaler öffentlicher Für-dich-Feed, soweit der Betreiber Zugriff hat.
- Ein eigener Tab wird geöffnet und nach dem Lauf geschlossen. Andere Tabs werden
  weder navigiert noch geschlossen. Keine Likes, Nachrichten, Kommentare oder externen
  Folgeaktionen. Zusätzliche Cookie-Nutzung wird bei einer bekannten Auswahl abgelehnt.
- Standardmäßig höchstens sechs Scroll-Schritte und 60 Sekunden je Plattform, einmal
  pro Entdecker-Lauf. Zwei Themen desselben Laufs starten keinen zweiten Browserlauf.
  Betreiberwerte werden auf höchstens zwölf Schritte/120 Sekunden begrenzt. Auch der
  Start des Browserprozesses besitzt eine separate harte Zeitgrenze.
- Nur sichtbare DOM-Karten zählen. Neue Karten, Scroll-Position und Veränderungen des
  sichtbaren Bereichs werden protokolliert. Eine bewegte Seite ohne erkannte Beiträge
  gilt nicht als erfolgreicher Inhaltsabruf.
- Die KI bewertet Texte/Beschreibungen. Videos erhalten zusätzliche Metadaten- und
  Sprachprüfungen. Eine vollständige Sichtung jedes Videos wird damit nicht belegt.
  Vor aufwendigen TikTok-Profil-/Hörprobenprüfungen wird ein Textbezug zu den eigenen
  Interessenthemen geprüft; passende zusätzliche Suchfunde können den Feed ergänzen.
- Login, Challenge und Ratenbegrenzung stoppen den Browserlauf. Bei aktiviertem
  Fallback kann der normale Such-/Quellenabruf weiterarbeiten; dessen Ergebnisse tragen
  weiterhin die Herkunft `index`, niemals fälschlich `browser_scroll`.
- Creator-Sperren, bestehende Abos, Gesehen/Merken und die maximale Vorschlagszahl
  gelten wie bisher. Ein Browser-Fund abonniert keinen Creator von selbst.

## Nachweis und Diagnose

`GET /api/discovery` mit Besitzer-Token liefert unter `browser` die wirksamen Grenzen
und `recent_scans`. Wichtige Felder: `scroll_steps`, `viewport_changed`,
`new_items_after_scroll`, `items_observed`, `stop_reason`. Ein erfolgreicher Browserlauf
braucht neue erkannte Inhalte nach tatsächlicher Bewegung. Kandidaten und Vorschläge
führen `discovered_via` sowie `browser_scan_id`. Bestehende Apps können Zusatzfelder
ignorieren. Detaillierte Rohdaten liegen privat in SQLite, nicht in öffentlichen Logs.

Standardmäßig werden keine Screenshots gespeichert. Für eine persönliche Diagnose
kann der direkte Adapter mit `--evidence` private Bilder unter dem eigenen
`data/browser-evidence` ablegen. Nicht in Git, Issues oder Releasepakete aufnehmen.
Browser-Kindprozesse erhalten keine App-, KI- oder Speech-Tokens über ihre Umgebung.
Der Debuggingzugang bleibt auf Server-Loopback und erhält keine öffentliche Route.

Automatisierte Prüfungen umfassen den Ablauf mit simulierten Plattformantworten sowie
echtes Chromium-Scrolling auf einer lokalen synthetischen Seite. Echte Plattformtests
müssen auf der jeweiligen eigenen Instanz erfolgen; Plattformverfügbarkeit und
dauerhafte Sitzungsstabilität sind damit nicht zugesichert.
