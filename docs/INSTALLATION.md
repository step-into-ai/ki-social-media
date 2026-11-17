# Installation

## Voraussetzungen und Grenzen

Linux amd64 oder arm64, Docker Engine mit Compose v2, Git, Python 3.12+ und ein
eigener HTTPS-Zugang. Für einen Pi ein 64-Bit-System mit ausreichend freiem Speicher
verwenden. Die Basisinstallation braucht keinen KI-Schlüssel und keine Anmeldung
bei YouTube oder TikTok. X und zusätzliche Spracherkennung sind optional.

Eine Instanz gehört einer Person. Es gibt keine voneinander getrennten Konten für
mehrere Nutzer innerhalb derselben Datenbank. Jeder Nutzer bekommt eine eigene
Instanz. Tokens und Sitzungen sind keine gemeinsam nutzbaren Projektdateien.

## 1. Projekt und private Konfiguration

```bash
git clone https://github.com/step-into-ai/ki-social-media.git
cd ki-social-media
python3 tools/manage.py init --url https://feed.example.org
```

Ersetze die Beispieladresse durch deine eigene erreichbare HTTPS-Adresse. `.env`
enthält jetzt drei unterschiedliche private Tokens. Die Datei bleibt Git-ignoriert.
`init` verweigert das Überschreiben einer vorhandenen Datei. Keine Tokens kopieren
oder von anderen Instanzen übernehmen. Noch sind keine Quellen abonniert.

## 2. Backend installieren

```bash
docker compose build
docker compose run --rm --no-deps --user 0 backend python tools/manage.py prepare-data
docker compose up -d
docker compose exec backend python tools/manage.py doctor
```

Der einmalige `prepare-data`-Aufruf setzt nur das dedizierte Datenverzeichnis auf
die Containerkennung 10001. Der eigentliche Dienst läuft ohne Root. Daten liegen
unter `./data`, Container-Neustarts erhalten sie. `doctor` prüft Gesundheit,
authentifizierte API und die Ablehnung eines Zugriffs ohne Schlüssel.

Host-Port 9131 muss frei sein. Falls belegt, ändere `CODY_PORT` in `.env`; passe
die HTTPS-Weiterleitung entsprechend an. Der interne Containerport bleibt 9131.

## 3. HTTPS einrichten

Das Backend ist absichtlich nur über `127.0.0.1:9131` des Hosts veröffentlicht.
Leite deinen eigenen HTTPS-Namen dorthin weiter. Für vorhandenes Caddy zeigt
`deploy/Caddyfile.example` einen einzelnen zusätzlichen Host. Passe nur die
eigene Route an und prüfe bestehende Routen vor und nach der Änderung.

Wenn du bereits Tailscale Serve/Funnel verwendest, kann eine eigene HTTPS-Route
denselben lokalen Dienst erreichen. Tailscale ist keine Backend-Abhängigkeit.
Überschreibe keine vorhandene Serve-Konfiguration. Bei einem privaten Tailnet-
Zugang braucht das Handy den entsprechenden Netzwerkzugang; ein bewusst öffentlich
bereitgestellter HTTPS-Zugang ist auch ohne Tailnet erreichbar.

Prüfe von außerhalb des Servers:

```bash
curl --fail https://feed.example.org/health
curl -i https://feed.example.org/api/sources
```

Erwartet: Gesundheit 200, persönliche Bibliothek ohne Token 401. Keine `-k`-Option.
Für einen Unterpfad kann der Reverse Proxy das Präfix entfernen; der mit der App
gekoppelte Basis-URL enthält dann diesen Unterpfad. Der historische Pfad
`/cody-social` wird zusätzlich direkt unterstützt.

## 4. Android verbinden

1. Die signierte APK von der offiziellen GitHub-Releaseseite laden.
2. Androids Installationserlaubnis für die verwendete Downloadquelle einschalten
   und die APK installieren. Keine Root-Rechte erforderlich.
3. Einen privaten Einmalcode erzeugen:

   ```bash
   docker compose exec backend python tools/manage.py pair
   ```

4. In KI Social Media die HTTPS-Adresse und den Code eintragen. Alternativ den
   ausgegebenen `kisocial://pair?...`-Link auf dem Handy öffnen. Dieser Link ist
   eine private Zugangsinformation und gehört nicht in ein öffentliches Ticket.
5. In Einstellungen eigene Quellen hinzufügen. Erst nach einem erfolgreichen
   echten Abruf erscheinen Inhalte. Die erste Auswahl umfasst bis zu fünf Videos
   je Creator/Format; später eintreffende ungesehene Inhalte bleiben erhalten.

Der Code gilt 30 Minuten und einmal. Ein neuer `pair`-Aufruf ersetzt den Code,
ohne bestehende App-Verbindungen oder den API-Token zu verändern.

Die öffentliche App hat die Paketkennung `de.stepintoai.kisocial`. Sie ersetzt
keine andere installierte App. Android-Nutzungsdaten und Überlagerung sind nur
für die optionale Mission-Self-Control-Funktion nötig.

## 5. Zusätzliche Funktionen

- [KI-Anbieter und Transkription](PROVIDERS.md)
- [Eigene X-Anmeldung](X.md)
- TikTok-Entdeckung mit echtem Sprachnachweis: einmalig

  ```bash
  docker compose exec backend python tools/setup_language.py
  ```

  Das kompiliert eine fest gepinnte whisper.cpp-Version und lädt ein per SHA-256
  geprüftes Tiny-Modell in `data/tiktok-language`. CPU und Speicher werden auf
  diesem Server benötigt. Die normale Sammlung abonnierter TikTok-Creator braucht
  diesen Zusatz nicht. Bei neuen Entdecker-Funden wird nur eine temporäre Hörprobe
  von bis zu zwölf Sekunden geprüft und danach gelöscht.

## Alternative ohne Docker

Für eigene Betriebsumgebungen kann die API mit Python 3.12 direkt laufen:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python tools/manage.py init --url https://feed.example.org
python tools/manage.py serve
```

Dieser Aufruf lädt `.env` und startet den lokalen Listener. Für einen dauerhaften
Dienst einen eigenen Prozessmanager einrichten. Optionalen KI-/Speech-Workern
müssen dieselben ausdrücklich ausgewählten Umgebungsvariablen mitgegeben werden.
Keine `.env` ungeprüft als Shellskript ausführen. Für Audio werden ffmpeg, für
optionale X-Werkzeuge deren eigene Browser-/Node-Voraussetzungen benötigt.
