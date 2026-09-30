# ZEIT-Radar

Scannt einmal täglich die Startseite von zeit.de, erkennt neu hinzugekommene Artikel
und zeigt sie getrennt nach **ZEIT ONLINE** und **DIE ZEIT** (Printausgabe) an.

Die Zuordnung erfolgt über die Artikeladresse:
DIE ZEIT liegt unter Jahr/Ausgabe (z. B. `zeit.de/2026/40/...`),
ZEIT ONLINE unter Ressort/Jahr-Monat (z. B. `zeit.de/politik/2026-09/...`).

## Einrichtung (einmalig, ca. 10 Minuten)

1. Kostenloses Konto auf https://github.com anlegen.
2. Oben rechts auf **+** → **New repository**. Name z. B. `zeit-radar`, Sichtbarkeit **Public**
   (nötig für die kostenlose Webseite), dann **Create repository**.
3. Auf der leeren Repo-Seite **uploading an existing file** anklicken und den **Inhalt**
   dieses Ordners hochladen (`scan.py`, `template.html`, `README.md` und den Ordner `.github`).
   Tipp: Der Ordner `.github` ist unter Windows/macOS evtl. versteckt; notfalls die Datei
   über **Add file → Create new file** mit dem Namen `.github/workflows/scan.yml` anlegen
   und den Inhalt hineinkopieren. Dann **Commit changes**.
4. Reiter **Actions** → ggf. Actions aktivieren → links **Täglicher ZEIT-Scan** →
   **Run workflow**. Nach ca. 1 Minute ist der erste Scan fertig (grüner Haken).
5. Reiter **Settings** → **Pages** → bei *Branch* `main` und Ordner `/docs` wählen → **Save**.
   Nach 1–2 Minuten erscheint dort der Link zu deiner Seite
   (`https://DEINNAME.github.io/zeit-radar/`). Als Lesezeichen speichern, fertig.

Ab dann läuft der Scan jeden Morgen automatisch.

## Anpassen

- **Uhrzeit:** in `.github/workflows/scan.yml` die `cron`-Zeile (Zeit in UTC).
- **Anzahl angezeigter Tage:** `SHOW_DAYS` oben in `scan.py`.

## Gut zu wissen

- Der erste Scan zählt alle Artikel als neu, ab dem zweiten Tag nur echte Neuzugänge.
- Gespeichert werden nur Titel und Links, keine Artikelinhalte.
- Falls zeit.de die Seitenstruktur ändert, stehen Hinweise unten auf der Webseite und im
  Reiter **Actions**. Ein roter Lauf bedeutet, dass an dem Tag nichts gefunden wurde.
