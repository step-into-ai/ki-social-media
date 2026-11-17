# KI Social Media

Dein eigener, endlicher Feed für YouTube, TikTok, X und RSS. Mit Android-App,
selbst gehostetem Backend und einer Anleitung für deinen KI-Agenten.

**[APK herunterladen](https://github.com/step-into-ai/ki-social-media/releases/tag/v0.1.0-beta.1)** ·
**[Installation](docs/INSTALLATION.md)** · **[Agentenanleitung](AGENTS.md)** ·
**[KI-Anbieter konfigurieren](docs/PROVIDERS.md)**

Erste öffentliche Beta: **0.1.0-beta.1**. Die App benötigt ein eigenes Backend.
Es gibt keinen mitgelieferten Gemeinschaftsserver und kein zentrales Benutzerkonto.

## Was die App bietet

- Lange YouTube-Videos unter Home, TikTok und YouTube-Shorts im wischbaren Short-Form-Feed.
- Gesehen/Gelesen, Merken, eigene Creator und ein Feed mit einem echten Ende.
- X-Beiträge und RSS-/Atom-Feeds unter News; optional deutsche Übersetzung.
- Optional Video-Zusammenfassungen und ein begrenzter Entdecker für neue Creator.
- Graphit und Papier als dunkles und helles Design.
- Optional Mission Self Control mit täglichen Öffnungs- und Zeitlimits für die
  Plattform-Apps. Android-Zugriffe werden nur dafür vom Nutzer eingeschaltet.

## Was du brauchst

- Android **10 oder neuer**; eine aktuelle Android System WebView.
- Einen eigenen Linux-Rechner, VPS oder Raspberry Pi mit 64-Bit-System, Docker
  Engine und Docker Compose v2. Python 3.12 ist für das Einrichten hilfreich.
- Eine HTTPS-Adresse für dein Backend, über einen vorhandenen Reverse Proxy oder
  einen selbst eingerichteten Zugang. Auf dem Handy wird diese Adresse gekoppelt.

Für den normalen Video-Feed und originale RSS-Texte ist **kein KI-Anbieter** nötig.
Für X wird eine eigene X-Sitzung benötigt. KI-Funktionen nutzen ausschließlich deine
ausdrücklich konfigurierten Anbieter und Modelle. **Hermes ist keine Voraussetzung.**

## Einrichtung in Kürze

```bash
git clone https://github.com/step-into-ai/ki-social-media.git
cd ki-social-media
python3 tools/manage.py init --url https://feed.example.org
docker compose build
docker compose run --rm --no-deps --user 0 backend python tools/manage.py prepare-data
docker compose up -d
docker compose exec backend python tools/manage.py doctor
docker compose exec backend python tools/manage.py pair
```

Die HTTPS-Weiterleitung auf den nur lokal freigegebenen Port 9131 richtest du vorher
oder anschließend nach der [vollständigen Anleitung](docs/INSTALLATION.md) ein.
Dann die signierte APK aus den Releases installieren, Serveradresse und Einmalcode
eingeben und die eigenen Quellen hinzufügen. Die Installation startet ohne fremde
Abos, gespeicherte Inhalte oder übernommene Anmeldungen.

## Einrichtung durch deinen Agenten

Du kannst deinem Agenten diesen Auftrag geben:

> Installiere KI Social Media aus https://github.com/step-into-ai/ki-social-media.
> Lies zuerst AGENTS.md. Nutze meinen vorgesehenen Server und vorhandenen
> HTTPS-Zugang. Starte zunächst ohne KI-Anbieter. Stelle mir nach den Prüfungen
> die APK und die private Kopplung bereit. Verändere keine anderen Dienste.

Der Agent hilft bei der Einrichtung. Danach läuft das Backend als normaler Dienst
weiter, auch ohne laufenden Agenten. Konfiguration und eigene Anpassungen sind in
[AGENTS.md](AGENTS.md) und [ARCHITECTURE.md](docs/ARCHITECTURE.md) beschrieben.

## Grenzen der Beta

Die Android-Oberfläche stammt aus einer persönlich verwendeten Einzelinstallation;
die öffentliche Paketkennung, Ersteinrichtung und Anbieteradapter sind neu. Build,
automatisierte Tests und frische Backend-Installationen ersetzen keinen Test auf
jedem Handy. Die genauen Nachweise stehen in [VALIDATION.md](docs/VALIDATION.md).

Plattformabrufe können durch Änderungen, Anmeldung, Regionen oder Abruflimits
ausfallen. X ist eine experimentelle optionale Anbindung. Die ältere Historie ist
auf den jeweils öffentlich abrufbaren Ausschnitt begrenzt. TikTok-Entdeckung braucht
zusätzlich die optionale lokale Sprachprüfung. Kontrollen und Abrufpausen werden
nicht umgangen. Ein VPS kann andere Ergebnisse liefern als ein Heimanschluss.

Der Player verwendet YouTube-/TikTok-Einbettungen. Dabei verbindet sich das Handy
mit der jeweiligen Plattform. Bei eingeschalteten KI-Funktionen gehen die dafür
benötigten öffentlichen Texte bzw. Audios an den gewählten Anbieter. Siehe
[Datenschutz und Zugänge](docs/PRIVACY.md).

## Entwicklung und Updates

```bash
python3 -m unittest discover -s tests -v
```

[Android bauen](docs/ANDROID.md) · [Sicherung und Updates](docs/OPERATIONS.md) ·
[Mitwirken](CONTRIBUTING.md) · [Sicherheitsmeldungen](SECURITY.md)

Der eigene Quellcode steht unter der [MIT-Lizenz](LICENSE). Fremdkomponenten behalten
ihre eigenen Lizenzen; siehe [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Dieses Projekt ist unabhängig von den genannten Plattformen.
