#!/usr/bin/env python3
"""remap_control_ids.py -- v1.0.0

Zieht eine Umnummerierung von Controls des Anwenderkatalogs Grundschutz++ durch die
Sammlung: Profile, Hilfsdateien (Caches der Pipeline), Mindeststandard-Exporte. Die
Zuordnung alt -> neu kommt aus den stabilen `alt-identifier`-UUIDs zweier Katalogstände
(Issue #52: Build 2026-11-23 der Stand-der-Technik-Bibliothek verschiebt 24 Controls in
DET.3, DET.5.10 und ASST.2; 13 alte IDs existieren weiter, zeigen aber auf ein anderes
Control). Deshalb laeuft die Ersetzung in EINEM Durchgang ueber die ganze Tabelle, nie als
Folge einzelner Suchen-und-Ersetzen-Schritte (DET.3.1.7 -> DET.3.1.1 waehrend
DET.3.1.1 -> DET.3.2.1).

Zwei Unterbefehle:

  derive  --alt <katalog-alt.json> --neu <katalog-neu.json> --alt-commit SHA --neu-commit SHA
          -o <moves.json>
      Vergleicht beide Staende ueber `alt-identifier` (Controls und Parameter) und schreibt
      die Tabelle: controls {alt: neu}, params {alt: neu}, dazu neue Controls, entfallene
      UUIDs und Controls mit geaendertem Titel/Statement bei gleichbleibender UUID.

  apply   --moves <moves.json> [--dry-run] <datei-oder-verzeichnis> ...
      Ersetzt in Textdateien (*.json, *.md, *.txt, *.py, *.csv) alle Vorkommen der alten
      IDs als Token: Control-IDs (Grossschreibung, auch als Praefix von `_stm`,
      `-m1_custom`, `#DET.3.1.1`) und Parameter-IDs (`det.3.3-prm1`). Ein Token ist eine
      ID, vor der kein [A-Za-z0-9._-] steht und auf die keine Ziffer, kein `.Ziffer` und
      kein Buchstabe folgt. Die Datei wird byteidentisch bis auf die Treffer
      zurueckgeschrieben (Formatierung bleibt). Nur stdlib.

Selbstpruefung von `apply`: nach dem Lauf enthaelt keine bearbeitete Datei mehr eine der
ENTFALLENEN alten IDs (die wiederverwendeten IDs sind naturgemaess weiter vorhanden, dann
aber mit neuer Bedeutung); die Anzahl der Treffer je Datei wird ausgegeben.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".csv"}


# ---------------------------------------------------------------- derive
def _walk_catalog(doc: dict):
    """Yields (control_id, alt_identifier, title, statement_prose, [(param_id, param_alt)])."""
    def ctl(c):
        alt = next((p["value"] for p in c.get("props", []) if p.get("name") == "alt-identifier"), None)
        stm = next((p.get("prose", "") for p in c.get("parts", []) if p.get("name") == "statement"), "")
        params = []
        for prm in c.get("params", []) or []:
            palt = next((p["value"] for p in prm.get("props", []) if p.get("name") == "alt-identifier"), None)
            params.append((prm["id"], palt))
        yield c["id"], alt, c.get("title", ""), stm, params
        for s in c.get("controls", []) or []:
            yield from ctl(s)

    def grp(groups):
        for g in groups or []:
            for c in g.get("controls", []) or []:
                yield from ctl(c)
            yield from grp(g.get("groups"))

    cat = doc["catalog"]
    yield from grp(cat.get("groups"))
    for c in cat.get("controls", []) or []:
        yield from ctl(c)


def derive(args) -> int:
    old = {alt: (cid, title, stm, params) for cid, alt, title, stm, params in _walk_catalog(json.loads(args.alt.read_text(encoding="utf-8"))) if alt}
    new = {alt: (cid, title, stm, params) for cid, alt, title, stm, params in _walk_catalog(json.loads(args.neu.read_text(encoding="utf-8"))) if alt}
    controls, params, changed, vanished = {}, {}, {}, []
    for alt, (ocid, otitle, ostm, oparams) in old.items():
        if alt not in new:
            vanished.append(ocid)
            continue
        ncid, ntitle, nstm, nparams = new[alt]
        if ncid != ocid:
            controls[ocid] = ncid
        # Parameter folgen ueber ihre eigene alt-identifier
        new_params_by_alt = {palt: pid for pid, palt in nparams if palt}
        for pid, palt in oparams:
            npid = new_params_by_alt.get(palt)
            if npid and npid != pid:
                params[pid] = npid
        # Inhaltliche Aenderung bei gleicher UUID, Parameter-IDs im Statement neutralisiert
        def neutral(stm, mapping):
            for a, b in mapping.items():
                stm = stm.replace(a, b)
            return stm
        if otitle != ntitle or neutral(ostm, params) != nstm:
            changed[ncid] = {
                "alt_id": ocid,
                "titel": None if otitle == ntitle else {"alt": otitle, "neu": ntitle},
                "statement": None if neutral(ostm, params) == nstm else {"alt": ostm, "neu": nstm},
            }
    new_controls = {cid: title for alt, (cid, title, _s, _p) in new.items() if alt not in old}
    out = {
        "meta": {
            "beschreibung": "Umnummerierung von Controls des Anwenderkatalogs Grundschutz++, ueber alt-identifier abgeleitet (Gpp-ai-tool/scripts/remap_control_ids.py derive).",
            "katalog_alt_commit": args.alt_commit,
            "katalog_neu_commit": args.neu_commit,
            "anzahl_verschoben": len(controls),
            "anzahl_parameter": len(params),
            "anzahl_neu": len(new_controls),
            "anzahl_geaendert_gleiche_uuid": len(changed),
            "hinweis": "controls und params in EINEM Durchgang anwenden (apply); 13 alte IDs existieren im neuen Stand weiter und bezeichnen ein anderes Control.",
        },
        "controls": dict(sorted(controls.items())),
        "params": dict(sorted(params.items())),
        "neue_controls": dict(sorted(new_controls.items())),
        "entfallene_uuids": sorted(vanished),
        "geaendert_gleiche_uuid": dict(sorted(changed.items())),
        "wiederverwendete_ids": sorted(set(controls) & (set(controls.values()) | set(new_controls))),
    }
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(controls)} Controls verschoben, {len(params)} Parameter, {len(new_controls)} neu, "
          f"{len(changed)} bei gleicher UUID geaendert, {len(vanished)} UUIDs entfallen, "
          f"{len(out['wiederverwendete_ids'])} IDs wiederverwendet -> {args.output}")
    return 0


# ---------------------------------------------------------------- apply
def build_pattern(ids: dict[str, str]) -> re.Pattern | None:
    if not ids:
        return None
    alts = sorted(ids, key=len, reverse=True)
    return re.compile(
        r"(?<![A-Za-z0-9._-])(" + "|".join(re.escape(i) for i in alts) + r")(?![0-9A-Za-z]|\.[0-9])"
    )


def remap_text(text: str, controls: dict[str, str], params: dict[str, str]) -> tuple[str, int]:
    """Ein Durchgang ueber alle Tokens: jede Fundstelle wird genau einmal ersetzt."""
    n = 0
    pat = build_pattern(controls)
    if pat:
        def sub(m):
            nonlocal n
            n += 1
            return controls[m.group(1)]
        text = pat.sub(sub, text)
    ppat = build_pattern(params)
    if ppat:
        def psub(m):
            nonlocal n
            n += 1
            return params[m.group(1)]
        text = ppat.sub(psub, text)
    return text, n


def iter_files(paths):
    for p in paths:
        p = Path(p)
        if p.is_dir():
            yield from (f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES)
        elif p.is_file():
            yield p
        else:
            print(f"WARNUNG: {p} nicht gefunden", file=sys.stderr)


def apply(args) -> int:
    moves = json.loads(args.moves.read_text(encoding="utf-8"))
    controls, params = moves["controls"], moves.get("params", {})
    # Parameter-IDs, die nur aus der Control-Verschiebung folgen, aber im Katalog keine eigene
    # alt-identifier tragen, werden aus den Control-Moves erzeugt (det.3.1.7-prm1 -> det.3.1.1-prm1).
    for a, b in controls.items():
        params.setdefault(a.lower(), b.lower())
    # Die Parameter-Tabelle enthaelt dann auch Eintraege ohne `-prm`; der Token-Lookahead
    # (kein Buchstabe/keine Ziffer danach) laesst `det.3.3` vor `-prm1` zu und verhindert
    # Treffer mitten in Woertern.
    removed = set(moves.get("entfallene_uuids", [])) | (set(controls) - set(controls.values()))
    total_files = total_hits = 0
    for f in iter_files(args.paths):
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text, n = remap_text(text, controls, params)
        if n == 0:
            continue
        total_files += 1
        total_hits += n
        print(f"  {n:5d}  {f}")
        if not args.dry_run:
            f.write_text(new_text, encoding="utf-8", newline="")
            check = build_pattern({i: i for i in removed})
            if check and check.search(new_text):
                print(f"FEHLER: {f} enthaelt nach dem Lauf noch eine entfallene ID", file=sys.stderr)
                return 1
    print(f"{'(dry-run) ' if args.dry_run else ''}{total_hits} Ersetzungen in {total_files} Dateien.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive", help="Zuordnung alt -> neu aus zwei Katalogstaenden ableiten")
    d.add_argument("--alt", type=Path, required=True)
    d.add_argument("--neu", type=Path, required=True)
    d.add_argument("--alt-commit", required=True)
    d.add_argument("--neu-commit", required=True)
    d.add_argument("-o", "--output", type=Path, required=True)
    d.set_defaults(func=derive)
    a = sub.add_parser("apply", help="Zuordnung in einem Durchgang auf Dateien anwenden")
    a.add_argument("--moves", type=Path, required=True)
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("paths", nargs="+")
    a.set_defaults(func=apply)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
