# Sicherung, Updates und Wiederherstellung

Die Compose-Instanz startet durch `unless-stopped` nach einem Serverneustart
wieder. Ein absichtlich gestoppter Dienst wird dadurch nicht eigenmächtig aktiviert.
Die Datenbank liegt unter `data/cody-social.db`; die Dateibezeichnung erhält den
API-/Migrationsvertrag der ursprünglichen App.

## Sicherung

```bash
docker compose exec backend python tools/manage.py backup
```

Die SQLite-Online-Sicherung enthält auch den korrekt übernommenen WAL-Zustand und
wird per `integrity_check` geprüft. Snapshots liegen privat in `data/backups`.
Nicht einfach eine laufende `.db` ohne WAL kopieren. Eine eigene regelmäßige
Sicherung und verschlüsselte externe Aufbewahrung werden vom Betreiber eingerichtet;
das Repository aktiviert keine fremden Cronjobs.

`.env` und benötigte eigene Sitzungsdaten separat verschlüsselt sichern. Sie
gehören nicht in Git oder öffentliche Releasepakete. Der APK-Signierschlüssel
wird nur vom jeweiligen APK-Maintainer aufbewahrt, nicht vom Backend benötigt.

## Backend-Update

1. Online-Sicherung erstellen und lokale Änderungen prüfen: `git status`.
2. Gewünschten Release/Commit bewusst auswählen. Eigene `.env` und `data` erhalten.
3. `git pull --ff-only`, dann `docker compose build` und `docker compose up -d`.
4. `docker compose exec backend python tools/manage.py doctor` ausführen und den
   externen HTTPS-Zugang sowie die gewünschten Quellen prüfen.

Ein fehlgeschlagener Abruf löscht keine bisherigen Inhalte. Bei Ratenlimits warten,
statt Anmeldung, Proxy oder Anbieter ohne Auftrag zu wechseln.

## Wiederherstellung

```bash
docker compose stop
docker compose run --rm --no-deps backend python tools/manage.py restore /data/backups/DEIN-SNAPSHOT.db --service-stopped
docker compose up -d
docker compose exec backend python tools/manage.py doctor
```

Der Helfer akzeptiert nur einen geprüften `.db`-Snapshot aus dem eigenen Backupordner
und erstellt vor dem Überschreiben eine weitere Sicherung. Alle Dienste müssen
tatsächlich gestoppt sein. Das Flag bestätigt diese vom Betreiber geprüfte Bedingung.

## Android-Update

Eine neue offizielle APK von GitHub Releases herunterladen und als Update installieren.
Paketkennung und Signatur bleiben bei offiziellen Updates gleich; App-Daten bleiben
dadurch erhalten. Der private Release-Schlüssel darf nicht gewechselt werden.
Es gibt in dieser Beta keinen stillen automatischen APK-Updater. Ein eigener Fork
braucht seine eigene Paketkennung und Signatur, wenn er neben dem Original läuft.

## Diagnose

`docker compose ps`, `/health`, `doctor` und die Quellenfehler in der App verwenden.
Keine `.env`, `pair`-Ausgabe oder Sitzungsdaten in Issues kopieren. Logs vor dem
Teilen prüfen. Die optionalen Drittwerkzeuge können eigene Diagnoseausgaben haben.
