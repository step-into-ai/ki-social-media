# Architektur und Adaptervertrag

Das Projekt setzt die Idee „Mein Agent doomscrollt für mich“ als automatisierte
Recherche und persönliche Vorauswahl um. Ein Einrichtungsagent hilft beim Aufbau
und bei Anpassungen. Die wiederkehrende Sammlung übernimmt danach das Backend;
gewünschte KI-Aufgaben übernehmen die konfigurierten Worker. Die Android-App ist
der Ort, an dem der Nutzer die vorbereiteten Inhalte bewusst auswählt.

```text
Android-App → eigene HTTPS-Adresse → Backend/API → SQLite im eigenen Datenvolume
                                     ├─ YouTube/TikTok/RSS-Sammler
                                     ├─ optionale X-Sitzung über Agent Reach
                                     ├─ optionaler KI-Worker → gewähltes Chat-Modell
                                     └─ optionaler Speech-Worker → gewählte Spracherkennung
```

Ein Backend ist ein persönlicher Datenbestand mit einem Besitzer-Token. Die drei
unterschiedlichen API-Tokens trennen Besitzer, Textworker und Speech-Worker. Ein
Worker-Token erhält keine allgemeinen Schreibrechte. Mehrbenutzerbetrieb innerhalb
einer Instanz ist nicht implementiert. Mehrere Personen betreiben getrennte Instanzen.

Die App verwendet einen bei der Kopplung gespeicherten Basis-URL. Sie erkennt
Erweiterungen über `/api/capabilities`. Öffentliche Routen: `/health` und isolierte
Playerseiten `/player/youtube/ID` bzw. `/player/tiktok/ID`. Persönliche Daten benötigen
Bearer-Authentifizierung; `/api/pair` akzeptiert einen zeitlich begrenzten Einmalcode.

Wichtige persönliche Endpunkte:

| Endpunkt | Bedeutung |
| --- | --- |
| GET /api/sources | Quellen und Abrufstatus |
| POST /api/source | Hinzufügen, Aktivieren, Ändern, Entfernen |
| GET /api/feed?format=long oder short | Ungesehene Videos, optional platform |
| GET /api/news | Gemischte Nachrichten |
| POST /api/video, /api/post, /api/seen | Gesehen/Gelesen/Merken |
| GET/POST /api/discovery | Entdeckerstatus und Einstellungen |
| POST /api/creator/block | Creator ausblenden/wieder zulassen |
| POST /api/suggestion | Abonnieren, Ablehnen, Stummschalten |

Die internen Arbeitsrouten `/internal/translation`, `/internal/editorial` und
`/internal/speech` verwenden Claim-/Ergebnisprotokolle. Identität und Texthash
verhindern veraltete Ergebnisse. Audioaufträge besitzen zusätzlich zeitliche Leases.
Anbieteradapter liegen in `collector/provider.py` und `collector/transcriber.py`.

Der Feed unterscheidet explizite YouTube-Videos-/Shorts-Reiter. Dauer allein ist
kein Formatnachweis. Entdeckte Videos müssen deutsche Audiosprache belegen;
TikTok nutzt dafür eine begrenzte lokale Hörprobe. Originale Nachrichten werden
vor einer Übersetzung vollständig abgerufen; Suchauszüge sind keine Nachrichten.

Sammlung und Nachrichtenredaktion dürfen getrennt scheitern. Bestehende Inhalte,
Merken und Gesehenstatus bleiben erhalten. Datenmigrationen erfolgen additiv beim
Start; ein Upgrade wird vorher gesichert.
