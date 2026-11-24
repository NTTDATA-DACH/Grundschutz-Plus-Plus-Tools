# Grundschutz++ OSCAL Tools – Version 5.3 (Bugfixing)

Version 5.3 ist ein reines Stabilitäts-, Korrektheits- und Sicherheits-Release. Es behebt zehn bestätigte Befunde aus den Browser-Werkzeugen (`GS++-oscal-app/`) und der Python-Pipeline (`Gpp-ai-tool/`) und ergänzt beide Bereiche um automatisierte Regressionstest-Suites (Playwright und pytest). Profil-, Katalog- und Mindeststandard-Artefakte bleiben unverändert — der Katalog-Pin `dc44ea4f` und der Selbst-Pin `1880842` aus Version 5.2 gelten unverändert weiter.

## Browser-Anwendungen (`GS++-oscal-app/`)

- **#1 Komponentenbezogene Prüfergebnisse (`pruefung_ap_ar.html`, `abarbeiten_POAM_generator.html`).** Prüfergebnisse werden nun durchgängig unter dem zusammengesetzten Schlüssel `(control-id, component-uuid)` statt nur pro `control-id` geführt. Beim OSCAL-1.2.2-AR-Export erhält jeder Befund seine saubere Zuordnung über `props` (`component-uuid`, `component-title`) und `subjects`; AR-Reimport und POA&M-Import übernehmen die Komponenten-UUID verlustfrei auch ohne Observation. Ältere AR-Dateien ohne Komponenten-UUID pro Befund werden weiterhin als rückwärtskompatibler Fallback gelesen.
- **#2 Sicherheit: XSS-Sanitizing, Session-Storage-Default & SRI (`gpp-core.js`, `GSpp-Viewer.html`, `config.html`, `pruefung_ap_ar.html`, `ssp_ausfuellen.html`, `Baustein_2_Profile.html`).**
  - Markdown- und KI-Ausgaben werden vor jeder `innerHTML`-Zuweisung (Cache-Treffer, frische Modellantwort und Fallback ohne `marked`) über einen Whitelist-HTML-Sanitizer (`gppSanitizeHtml` / `gppRenderMarkdown`) bereinigt (`<script>`, `<iframe>`, `on*`-Handler sowie `javascript:`/`data:`-URLs werden entfernt; der Fallback ohne `marked` escaped vollständig).
  - API-Keys (`ai:key:*`) und GitHub-Token (`gh:token`) verbleiben standardmäßig nur in `sessionStorage` bzw. im Speicher statt in `localStorage`. Eine explizite Opt-in-Option in `config.html` (*„Im Browser dauerhaft speichern (localStorage)“*, standardmäßig aus) erlaubt bei Bedarf persistentes Speichern und bereinigt bestehende Werte beim Abschalten.
  - Alle CDN-Skripte (`marked@15.0.0`, `pdf.js@3.11.174`, `mammoth@1.8.0`) sind auf feste Versionen gepinnt und mit verifizierten `integrity="sha384-..."`-Hashes sowie `crossorigin="anonymous"` abgesichert.
- **#3 Offline-Delete mit Compare-and-Swap (`gpp-core.js`).** Offline vorgemerkte Löschungen führen ihre Basis-SHA (`baseSha`) in der Outbox mit und löschen beim Sync per PostgREST-CAS (`id=eq.<id>&sha256=eq.<baseSha>` mit `Prefer: return=representation`). Werden 0 Zeilen gelöscht und existiert das Artefakt remote mit neuerer SHA weiter, meldet der Client einen expliziten Löschkonflikt zur Nutzerentscheidung, statt die zwischenzeitlich geänderte Server-Version still zu entfernen.
- **#4 Excel-Roundtrip mit Export-Baseline & Drei-Wege-Konfliktdialog (`ssp_ausfuellen.html`).** Der Excel-Export schreibt ein verstecktes Blatt `_gpp_baseline` mit dem genauen Exportstand aller Controls und Parameter mit. Beim Re-Import führt die App einen Drei-Wege-Abgleich (*Baseline vs. aktueller SSP vs. Excel*) durch: Unveränderte Excel-Zellen überschreiben neuere SSP-Änderungen nicht mehr; bei echten Konflikten (beide Seiten gegenüber der Baseline geändert) öffnet sich ein Konfliktdialog zur gezielten Auswahl je Feld. Ältere Workbooks ohne `_gpp_baseline` werden mit einer klaren Warnung behandelt.
- **#8 Atomares Release-Manifest statt ungewarntem Einzel-Repinning (`gpp-core.js`, `config.html`, `ssp_generator.html`, `GSpp-Viewer.html`).** Katalog-, Mapping-, Tools- und Mindeststandard-Pins werden über ein gemeinsames atomares Release-Manifest (`gppReleaseManifest`, `release-5.2`) verwaltet und in Profil-/SSP-Exporte übernommen. Einzel-Overrides in `config.html` greifen nur noch im expliziten Experten-Modus hinter einer Kompatibilitätswarnung.
- **#9 Echte NG-Import- und Hash-Prüfung im Explorer (`GSpp-Viewer.html`).** `NG-`-Control-IDs werden nicht mehr pauschal als Treffer gezählt. Jeder Profil-Import wird einzeln aufgelöst und gegen seinen SHA-256-Hash in der Back-Matter-Resource geprüft; fehlende, nicht ladbare oder hash-abweichende NG-Ergänzungskataloge erscheinen klar als Fehler statt als Falsch-Grün.

## Python-Pipeline (`Gpp-ai-tool/`)

- **#5 Striktes Checker-Freigabegate (`stage_ng_katalog.py`, `stage_ED23_profiles_enhanced.py`).** Der NG-Katalog und die angereicherten ED23-Profile verlangen eine explizite Checker-Freigabe; fehlerhafte oder unbestätigte Checker-Läufe werden nicht mehr still als „erledigt“ gecacht oder in Ausgaben übernommen.
- **#6 Deterministisches Input-Hash-Caching (`stage_ed23_baustein_abgleich.py`, `stage_ed23_anforderungen.py`, `src/utils/ed23_baustein.py`).** Cache-Einträge speichern einen deterministischen `input_hash` über den vollständigen fachlichen Eingang (u. a. Control-/Anforderungstexte und relevante Parameter). Bei geänderten Eingaben werden nur die tatsächlich betroffenen Einträge gezielt neu berechnet statt veraltete Ergebnisse weiterzuverwenden.
- **#7 Idempotenz & Quellstand-Prüfung beim Control-ID-Remap (`scripts/remap_control_ids.py`).** `remap_control_ids.py` prüft vor dem Umschreiben den Quellstand und verhindert per Fail-Closed-Sicherung doppelte Permutationsläufe auf bereits umgeschriebenen Dateien.

## Automatisierte Regressionstests (#10)

- **Browser-Apps (`GS++-oscal-app/tests/`):** Schlanke Playwright-Regressionstestsuite über lokalen HTTP-Server mit 6 fokussierten Tests für #1, #2, #3, #4, #8 und #9.
- **Python-Pipeline (`Gpp-ai-tool/tests/`):** Offline-pytest-Suite für #5, #6 und #7 (`test_stage_ng_katalog.py`, `test_stage_ED23_profiles_enhanced.py`, `test_stage_ed23_baustein_abgleich.py`, `test_stage_ed23_anforderungen.py`, `test_remap_control_ids.py`).

## Versionen der Anwendungen

| Anwendung | Version |
|---|---|
| gemeinsamer Kern (gpp-core.js) | 4.2 · Cache-Buster v4.2 |
| gemeinsames Stylesheet (gpp-core.css) | 2 · Cache-Buster v4.1 (unverändert) |
| Übersicht (index.html) | 1.8 · Kern-Cache-Buster v4.2 |
| OSCAL Schema Validator | 1.11.2 · Kern-Cache-Buster v4.2 |
| SSP-Generator / Editor (ssp_generator) | V5.18.3 · Atomares Release-Manifest |
| GS++ Explorer (GSpp-Viewer) | v9.12 · XSS-Sanitizing, SRI, NG-Import-/Hash-Prüfung, Release-Manifest |
| BSI → G++ Profil (Baustein_2_Profile) | 0.12.2 · pdf.js-SRI |
| SSP ausfüllen / Grundschutzcheck (ssp_ausfuellen) | v1.7.4 · Excel-3-Wege-Merge & Konfliktdialog, XSS-Sanitizing, SRI |
| Prüfung AP/AR (pruefung_ap_ar) | build 9.7.2 · Komponentenbezogene Befunde, XSS-Sanitizing, SRI |
| POA&M-Generator | v2.7 · Komponenten-UUID-Erhalt ohne Observation |
| Pipeline (Gpp-ai-tool) | 5.3.0 · Checker-Gate, Input-Hash-Caching, Remap-Idempotenz, pytest-Suite |

## Kompatibilitäts- und Migrationshinweise

- **Einmal mit Strg+F5 laden.** `gpp-core.js` trägt den neuen Cache-Buster `v=4.2`, sodass Browser den aktualisierten Kern sauber nachladen.
- **API-Keys & GitHub-Token (Session-Storage-Default):** Bisher in `localStorage` abgelegte Schlüssel bleiben beim ersten Start lesbar, neue Einträge landen standardmäßig nur noch in `sessionStorage` (Tab-Sitzung). Wer dauerhafte Speicherung im Browser ausdrücklich wünscht, aktiviert in `config.html` die Opt-in-Option *„Im Browser dauerhaft speichern (localStorage)“*.
- **Ältere `hilfsdateien/`-Caches ohne `input_hash`:** Bestehende Pipeline-Caches aus Version 5.2 ohne `input_hash`-Feld werden beim nächsten Pipeline-Lauf als veraltet erkannt und sauber auf das neue Cache-Format mit `input_hash` aktualisiert.
- **Bestehende OSCAL- und Excel-Dateien:** Ältere AR-Dateien ohne `component-uuid`-Prop sowie ältere Excel-Exporte ohne `_gpp_baseline`-Blatt bleiben weiter lesbar (mit Fallback bzw. Warnhinweis).
- **Pins unverändert:** Da keine Profil-, Katalog- oder Mindeststandard-Artefakte verändert wurden, bleiben der Katalog-Pin `dc44ea4f` (`9497c7a9…`) und der Selbst-Pin `1880842` aus Release 5.2 unverändert gültig.
- **Auslieferung:** `GS++-oscal-app/GS++-oscal-app.zip` enthält wie bisher exakt die zwölf Distributionsdateien (ohne `tests/` und `node_modules/`).
