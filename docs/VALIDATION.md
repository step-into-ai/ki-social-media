# Prüfung der öffentlichen Beta

Version: **0.1.0-beta.1**. Die öffentliche Fassung ist eine getrennte Exportkopie;
die private laufende App, deren Signierschlüssel und das ursprüngliche Pi-Backend
werden dadurch weder aktualisiert noch verändert.

## Automatisierte Prüfungen

- Backend-Regressionsprüfungen für Formattrennung, endlichen Feed, Erhalten von
  Gesehen/Merken, Creator-Sperren, RSS und Entdecker-Inhalte.
- Portabilitätsprüfungen: leere Erstinstallation, originales News-Lesen ohne KI,
  frei gewählte Chat-/Speech-Endpunkte und Modelle, lokale Anbieter ohne API-Key,
  Ablehnung ungewollten HTTPs und von Zugangsdaten in API-URLs.
- Zufällige unterschiedliche Instanztokens, Erhalt vorhandener Konfiguration,
  Ablauf/Einmalverwendung/Erneuerung der Kopplung, getrennte Worker-Rechte.
- Online-Sicherung, Integritätsprüfung und Wiederherstellung einer ganzen SQLite-DB.
- Android-Unit-Tests, Release-Build, Lint und Prüfung der eigenen Release-Signatur.
- GitHub Actions: unabhängige Python-Tests, Debug-Android-Build und Containerbau mit
  frischem Installations-/Kopplungs-/Neustarttest auf Linux amd64 und arm64.

Aktuelle tatsächliche Laufergebnisse: [GitHub Actions](https://github.com/step-into-ai/ki-social-media/actions).
Nur grüne abgeschlossene Läufe gelten als bestanden. Releasehinweise nennen den
geprüften Stand; spätere fehlgeschlagene Läufe werden dadurch nicht grün erklärt.

## Was diese Prüfungen nicht belegen

Die öffentlichen Anbieteradapter werden mit synthetischen kompatiblen HTTP-Servern
geprüft. Es wurde kein fremder kostenpflichtiger Anbieterzugang verwendet. Ein
Betreiber prüft seinen gewählten Anbieter und die Übersetzungsqualität selbst.

Die öffentliche APK hat eine neue Paketkennung und eigene Signatur. Es wurde kein
Update auf dem privaten Handy installiert. Die persönlich genutzte Vorläufer-App
ist kein eigener Handytest dieser öffentlichen Variante. Gerätespezifische
Wiedergabe, Gesten und Mission-Rechte müssen bei neuen Installationen geprüft werden.

Eine frische leere Containerbibliothek belegt keine angemeldete X-Sitzung und keinen
aktuellen Plattformabruf. Die optionalen Browserintegration und lokale Sprachprüfung
benötigen jeweils Einrichtung und einen echten inhaltlichen Test beim Betreiber.
Mehrtägiger Betrieb und alle Cloudanbieter sind keine bestandenen CI-Testfälle.
