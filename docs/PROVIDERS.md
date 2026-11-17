# Eigene Anbieter und Modelle

Das Backend liest keine fremde Hermes-Konfiguration und enthält kein fest
vorgegebenes KI-Modell. Der Betreiber wählt Endpunkt, Modell und ggf. API-Schlüssel.
Die Namen `CODY_*` bezeichnen interne Dienstschnittstellen aus der ursprünglichen
App; sie verlangen weder einen Cody- noch einen Hermes-Agenten.

## Übersetzung, Zusammenfassung und Entdecker

Der Adapter erwartet eine OpenAI-kompatible Chat-Completions-Schnittstelle.
In `.env` setzen:

```dotenv
AI_ENABLED=true
AI_BASE_URL=https://DEIN-ANBIETER/v1
AI_MODEL=DEINE-MODELLKENNUNG
AI_API_KEY=DEIN-EIGENER-SCHLUESSEL
COMPOSE_PROFILES=ai
```

`AI_BASE_URL` endet vor `/chat/completions`. Es kann etwa ein direkt gebuchter
Anbieter, ein Router oder ein selbst betriebener kompatibler Modellserver sein.
Für lokale Endpunkte darf der Schlüssel leer sein. Unverschlüsseltes HTTP wird nur
mit `AI_ALLOW_HTTP=true` zugelassen und sollte ausschließlich für den ausdrücklich
gewählten lokalen Dienst verwendet werden. Im Container bezeichnet `localhost`
den Container selbst. Nutze einen im Container erreichbaren Hostnamen.

Das Modell muss System-/Benutzernachrichten, ausreichende Kontextlänge und valide
JSON-Ausgaben unterstützen. Ein kompatibler API-Pfad garantiert keine gleiche
Qualität aller Modelle. `AI_TOKEN_LIMIT_FIELD` ist standardmäßig `max_tokens`,
alternativ `max_completion_tokens` oder leer, falls der Anbieter das Feld ablehnt.

```bash
docker compose up -d
docker compose exec ai python tools/check_provider.py
```

Der Check sendet nur einen kurzen synthetischen Satz. Er kann einen API-Aufruf
berechnen lassen. Danach eine echte Übersetzung prüfen. Der Entdecker bleibt
anfangs ausgeschaltet und wird unter Einstellungen bewusst aktiviert. Themen,
Plattformen und höchstens drei Vorschläge pro Lauf sind dort einstellbar.

Ohne KI zeigt News Originaltexte. Zusammenfassungen und KI-Auswahl stehen dann
nicht zur Verfügung. Ein temporärer Anbieterfehler wird angezeigt und später
erneut versucht; es wird kein anderer Anbieter automatisch belastet.

## Optionale Cloud-Transkription

Fehlen öffentliche Untertitel, kann der eigene Speech-Worker eine Audiospur
vorübergehend herunterladen und transkribieren. Er ist standardmäßig deaktiviert.

```dotenv
SPEECH_PROVIDER=compatible
SPEECH_BASE_URL=https://DEIN-SPRACHANBIETER/v1
SPEECH_MODEL=DEINE-TRANSKRIPTIONSMODELLKENNUNG
SPEECH_API_KEY=DEIN-EIGENER-SCHLUESSEL
COMPOSE_PROFILES=ai,speech
```

Erwartet wird `/audio/transcriptions`, Multipart-Felder `model`, `file` und
`response_format=json` sowie eine Antwort mit `text`. Bei lokalen kompatiblen
Endpunkten gilt `SPEECH_ALLOW_HTTP=true` nach derselben bewussten Entscheidung.
Es wird kein Modellname für den Anbieter geraten und kein Hermes-Prozess benötigt.

Der Download verwendet keine Browseranmeldung und keine Proxys. Die vollständige
Audiospur wird nach Mono-AAC komprimiert; bleibt sie an/über 24 MB, wird abgebrochen.
Eine gekürzte Audiospur wird niemals als vollständiges Video zusammengefasst.
Sperren und Limits führen zu einem sichtbaren Fehler, nicht zu einer Umgehung.
Temporäre Audiodateien werden nach Erfolg oder Fehler gelöscht.

## Optionale lokale Transkription

Nach `tools/setup_language.py` steht ein kleines whisper.cpp-Modell zur Verfügung:

```dotenv
SPEECH_PROVIDER=local
SPEECH_LOCAL_BIN=/data/tiktok-language/whisper-cli
SPEECH_LOCAL_MODEL=/data/tiktok-language/ggml-tiny-q5_1.bin
COMPOSE_PROFILES=ai,speech
```

Alternativ ein eigenes kompatibles whisper.cpp-Modell im eigenen Volume hinterlegen.
Tiny ist für die kurze Sprachprüfung gedacht und bietet begrenzte Textqualität;
vollständige lange Transkripte brauchen mehr Rechenzeit und ggf. ein größeres Modell.
Es erfolgt kein automatischer Wechsel zwischen Cloud und lokaler Erkennung.
