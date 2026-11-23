# Grundschutz++ OSCAL Tools – Version 5.2

Version 5.2 zieht die Sammlung auf den **Build 2026-11-23 der Stand-der-Technik-Bibliothek** (Commit `dc44ea4f`, Merge des BSI-PR #118 vom 2026-11-23) und löst Issue #52: Der Build nummeriert **24 Controls** in den Praktiken DET.3, DET.5.10 und ASST.2 um. Die `alt-identifier`-UUIDs sind dabei stabil geblieben, die IDs nicht, und 13 alte IDs bezeichnen jetzt ein anderes Control (`DET.3.1.1` war „Authentifizierungen“ und ist jetzt „Was, Wann, Wo“). Ein Profil, das die alte ID weiter verwendet, löst also weiter auf, aber auf den falschen Inhalt. Deshalb wurden alle Profile, die Pipeline-Caches und die acht Mindeststandard-Stände über die UUID-Tabelle in einem Durchgang umgeschrieben und die Profile gegen den neuen Pin neu erzeugt; das neue Control `DET.3.2` „Protokollierung in IT-Systemen“ und zwölf umformulierte Controls wurden gegen die Edition 2023 neu abgeglichen.

## Was sich in der Bibliothek geändert hat (160c177d → dc44ea4f)

- **Umnummerierung (24 Controls, UUIDs stabil).** `ASST.2.3.2` → `ASST.2.4` (SBOM), `ASST.2.3.2.1` → `ASST.2.4.1`, `ASST.2.4` → `ASST.2.5` (Klassifizierung); unter `DET.3.1` „Protokollierung in Anwendungen“ (bisher „Protokollierung sicherheitsrelevanter Ereignisse“) bleiben die anwendungsbezogenen Ereignisse als `DET.3.1.1`–`DET.3.1.5` (vorher `DET.3.1.7`–`DET.3.1.11`), die systembezogenen wandern unter das **neue** Control `DET.3.2` „Protokollierung in IT-Systemen“ als `DET.3.2.1`–`DET.3.2.6` (vorher `DET.3.1.1`–`DET.3.1.6`), `DET.3.1.12` wird `DET.3.3`, und `DET.3.2`–`DET.3.6` rücken auf `DET.3.4`–`DET.3.8`; in DET.5.10 werden die automatisierten Update-Überwachungen zu `DET.5.11` und `DET.5.12`, Integritätsprüfung und Test rücken auf `DET.5.10.2` und `DET.5.10.3`. Die vollständige Tabelle alt → neu samt Parameter-IDs steht in `hilfsdateien/control_id_moves_160c177d_dc44ea4.json` (aus den `alt-identifier` abgeleitet, `Gpp-ai-tool/scripts/remap_control_ids.py derive`). Anwenderkatalog 1000 → 1001 Controls.
- **Umformuliert bei gleicher UUID (14 Controls).** ASST.2.1 und ASST.2.3 nennen jetzt die Zielobjektkategorie im Statement („Informationen und Assets für Daten SOLLTE …“, „… für IT-Systeme SOLLTE …“), KONF.15.2 bekommt einen Parameter („Rechenleistung pro {{…}} einschränken“), KONF.2.6 heißt „Mobile Device Management“ (bisher „Automatische Konfigurationsverwaltung“), weitere neue Titel bei DET.3.1, GEB.8.1.1, ARCH.2.2.1, KONF.2.3, KONF.2.5, KONF.9.2, KONF.10.3, KONF.15.3; BES.7.4.7 und BES.7.4.12 haben erweiterte Guidance.
- **Werte der `documentation`-Prop.** `Beschaffungskriterien` → `Leistungsbeschreibung` (70 Controls), `Detektions-Konzept` → `Detektionskonzept` (61), `Outsourcing Strategie` → `Outsourcing-Strategie`, `Übungsplan`/`Prüfplan` → `Übungs- und Prüfplan`, `Anwendungsdokumentation`/`Systemdokumentation` → `Betriebshandbuch`, `Prozess Behandlung von Sicherheitsvorfällen` → `Behandlung von Sicherheitsvorfällen`; `documentation_guidelines.csv` entsprechend neu geschnitten (`Schwachstellenregister` neu, `Verfahrensbeschreibung` mit echter Definition). Prop-Namen unverändert; keine App verdrahtet `documentation`-Werte fest.
- **Kataloge.** `control_layer/WLAN/` ist entfallen, ersetzt durch `WLAN-Enterprise` (53 IDs) und `WLAN-Einzelplatz-und-Gastnetze` (44 IDs, zusätzliche Gruppe WLAN.7). Neu: `DIVA` („Durchgängige Identitätsprüfung, Verifikation und Absicherung“, 168 Controls, alle auch im Anwenderkatalog). GSMap, `target_object_categories.csv` und `security_level.csv` sind byte-identisch; `action_words.csv` präzisiert „dokumentieren“.

## Repin: Anwenderkatalog dc44ea4f in Werkzeugen, Pipeline und Profilen

- Pin `dc44ea4fb5815ef84b941a8b5bcc4eaf363daf35`, SHA-256 `9497c7a9…`, Resource-UUID `1743f782-c978-51fd-acd0-81168bc1727f` (uuid5 der gepinnten URL) in den sechs Werkzeugen der Sammlung, in `one-page-apps/mindeststandard-oscal.html`, in `Gpp-ai-tool/src/constants.py` und in allen Profilen.
- **Umschreiben statt Suchen/Ersetzen.** `Gpp-ai-tool/scripts/remap_control_ids.py apply` ersetzt alle alten IDs als Token in **einem** Durchgang (Control-IDs, `_stm`- und `-m1_custom`-Part-IDs, Parameter-IDs wie `det.3.3-prm1`, Fragment-Links und Linktexte) in den Profilen und den Pipeline-Caches (`ed23_baustein_abgleich.json`, `ed23_maturity_cache.json`, `gpp_ed23_anforderungen.json`, `prozessbausteine_mapping.json`, `ed23_satz_abdeckung.json`): 11 972 Token-Ersetzungen in 127 Dateien (97 ED23-Baustein-Profile, 23 Zielobjekt- und Praktikenprofile, 6 Caches, die Pipeline-Kopie des Prozessmappings). Die Tabelle ist eine Permutation und darf je Datei nur einmal laufen.
- **Profile neu erzeugt.** Stufe 1 und 3 der Pipeline gegen den neuen Pin: 39 Zielobjekt- und 17 Praktiken-Basisprofile; das neue `DET.3.2` steht in den Pools IT-Systeme, Hostsysteme und Mobile Endgeräte. Stufe 8 (ED23-Baustein-Profile) mit den umgeschriebenen Caches: 194 Profile neu geschrieben (97 Bausteine, plain und `_enhanced`), 3496 Reifegrad-Blöcke aus dem Cache, 47 neu erzeugt (38 Modellaufrufe: `DET.3.2` sowie ASST.2.1, ASST.2.3 und KONF.15.2 mit neuem Statement), `ED23-Baustein-profile/pruefe_export.py` gegen den neuen Anwenderkatalog: 194 Profile, 69 NG-Controls, 0 Befunde. Stufe 9 (Praktiken-Prozessprofile, `_enhanced`) liest jetzt wie Stufe 8 zuerst den Reifegrad-Cache (Schlüssel `prozess:<stem>`) und fragt das Modell nur für Controls ohne gültigen Eintrag: 17 Praktikenprofile neu erzeugt, 358 von 362 Controls aus dem Cache, 4 neu (je 2 in BER und Methodik); der ASST-Pool schrumpft auf 10 Controls, weil `ASST.2.4` (SBOM) und `ASST.2.4.1` jetzt Zielobjektkategorien tragen.
- **Edition 2023 neu abgeglichen.** `stage_ed23_anforderungen` lief inkrementell (Checkpoint aus dem umgeschriebenen Mapping) nur für das neue `DET.3.2` und die zwölf Controls mit neuem Titel oder Statement; `stage_ed23_relationen` für dieselben Controls: 173 Modellaufrufe, 77 Prüfungen über die Satz-Abdeckung gespart; `DET.3.2` erhält 21 Anforderungsbezüge (u. a. NET.1.2.A7, NET.3.1.A7, SYS.4.4.A18), `KONF.2.6` als „Mobile Device Management“ wechselt auf die SYS.3.2.x-Anforderungen (9 → 16 Bezüge), `ARCH.2.2.1` „Externe Netzanschlüsse einschränken“ 10 → 22, `KONF.2.3` 10 → 18; insgesamt 5086 → 5140 Paare, 866 Controls mit Treffern. Relationen: 180 Paare klassifiziert, 42 vom Standard `intersects-with` abweichend (37 `superset-of`). Der Abgleich (Stufe 6) verwendet seine Checker-Urteile weiter, weil die umgeschriebenen IDs im neuen Katalog auflösen: 1871 Anforderungen in 97 Bausteinen, 1521 deterministisch, 350 Checker-Urteile wiederverwendet, 0 Modellaufrufe; 111 Anforderungen mit geänderter Zuordnung (davon 20 neu mit `DET.3.2`), weiterhin 69 NG-Controls und 5 Anforderungen ohne Control. NG-Ergänzungskatalog: 69 Controls, SHA-256 `23b9a008…` (die Links auf den Anwenderkatalog zeigen auf den neuen Pin, die Praktik-Links auf die neuen IDs), in den importierenden Profilen nachgezogen.
- **Mindeststandards.** Alle acht Stände mit `mindeststandards/repin.py --id-map` umgestellt und neu aufgelöst; betroffen von der Umnummerierung sind PD (6 Controls), MDM (3), NCD (1) und WB (1). `repin.py` kennt die umbenannten `documentation`-Werte als mechanisch (`DOC_RENAMES`), vergleicht Controls ohne ihre Kind-Controls und hebt den alten Stand vor dem Vergleich auf die neuen IDs (auch die `related`-Links). Übernommen in neuer Fassung (`--accept-changed`): die oben genannten 14 Controls, soweit ein Stand sie verwendet; die Remarks nennen sie. `pruefe_export.py`: 0 Befunde; `repin.py --check-only`: Resolver und Textform identisch. SHA-256 der acht Profile in `MST_PINNED` des SSP-Generators nachgezogen.
- `check_pins.py`: __CHECK_PINS__.

## GS++ Explorer v9.11: DIVA, WLAN und Lieferkette in der Schnellauswahl

`STDT_PIN` auf `dc44ea4f`; die Schnellauswahl und die Quellen-Registrierung (Pin-Übersicht in `config.html`) kennen zusätzlich die aufgelösten Kataloge Lieferkettensicherheit, DIVA, WLAN-Enterprise und WLAN-Einzelplatz- und Gastnetze.

## Hinweis für eigene SSPs und Profile

OSCAL referenziert Controls über ihre ID. Wer SSPs, Profile, Prüfpläne oder POA&Ms gegen den Stand `160c177d` erstellt hat und sie auf den neuen Katalog hebt, muss die 24 Umnummerierungen nachziehen, sonst zeigen 13 Referenzen stillschweigend auf andere Controls. Die Tabelle `hilfsdateien/control_id_moves_160c177d_dc44ea4.json` und `remap_control_ids.py apply --moves … <datei>` erledigen das in einem Durchgang; gespeicherte Dateien mit Back-Matter-Pin auf `160c177d` bleiben unter ihrer Commit-URL weiter korrekt auflösbar.

## Versionen der Anwendungen

| Anwendung | Version |
|---|---|
| gemeinsamer Kern (gpp-core.js) | 4 · Cache-Buster v4.1 |
| gemeinsames Stylesheet (gpp-core.css) | 2 · Cache-Buster v4.1 |
| Übersicht (index.html) | 1.8 |
| OSCAL Schema Validator | 1.11.2 |
| SSP-Generator / Editor (ssp_generator) | V5.18.2 · Katalog-Pin, MST-Hashes, Selbst-Pin |
| GS++ Explorer (GSpp-Viewer) | v9.11 · neue SdT-Kataloge |
| BSI → G++ Profil (Baustein_2_Profile) | 0.12.1 · Katalog-Pin, Selbst-Pin |
| SSP ausfüllen / Grundschutzcheck (ssp_ausfuellen) | v1.7.3 · Katalog-Pin, Selbst-Pin |
| Prüfung AP/AR (pruefung_ap_ar) | build 9.7.1 · Katalog-Pin, Selbst-Pin |
| POA&M-Generator | v2.6 · Katalog-Pin |
| Pipeline (Gpp-ai-tool) | 5.2.0 · Katalog-Pin, `remap_control_ids.py`, Reifegrad-Cache in Stufe 9 |

Einzelwerkzeuge in `one-page-apps/`: eigenständig, ohne `gpp-core.js`, von der Datenbank unberührt:

| Anwendung | Version |
|---|---|
| SSP-Generator Edition 2023 | ED23 V1.7.1 · nur Selbst-Pin |
| C5 → OSCAL Konverter | v1.1 · unverändert |
| Mindeststandard → OSCAL | build 1.4.2 · Katalog-Pin |

## Hinweise zum Umstieg

- **Einmal mit Strg+F5 laden.** Kern und Stylesheet sind unverändert.
- Die Selbst-Pins (`GPP_TOOLS_PIN_COMMIT`, `MST_PIN_COMMIT`, `GPPT_PIN`) zeigen auf Commit 1 dieses Releases, den Stand mit den neu erzeugten Profilen (zweiter Commit „Selbst-Pin auf …“, ZIP neu gebaut).
- Neu erzeugte Profile, SSPs, Prüfpläne und POA&Ms nennen in ihrer Back-Matter die neue Katalog-Resource (URL mit `dc44ea4f`, SHA-256 `9497c7a9…`, UUID `1743f782…`). Ältere Dateien verweisen weiter auf `160c177d`, der unter seiner Commit-URL erreichbar bleibt.
- Das Handbuch (Kapitel 3, v0.16) behält den Build 2026-10-22 als Bezugsstand; die Methodik-Controls (GC, STM, UMS, VRB, PERF) sind im neuen Build unverändert, nur Anhang B (Dokumentenlandkarte) wird mit dem nächsten Handbuchstand an die neu geschnittene `documentation_guidelines.csv` angepasst.
- Die Auslieferung bleibt `GS++-oscal-app.zip` (zwölf Dateien); eine einzelne HTML-Datei allein läuft nicht.
