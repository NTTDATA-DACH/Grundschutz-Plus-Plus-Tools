#!/usr/bin/env python3
"""remap_control_ids.py -- v1.1.0

Zieht eine Umnummerierung von Controls des Anwenderkatalogs Grundschutz++ durch die
Sammlung: Profile, Hilfsdateien (Caches der Pipeline), Mindeststandard-Exporte. Die
Zuordnung alt -> neu kommt aus den stabilen `alt-identifier`-UUIDs zweier Katalogstaende
(Issue #52: Build 2026-11-23 der Stand-der-Technik-Bibliothek verschiebt 24 Controls in
DET.3, DET.5.10 und ASST.2; 13 alte IDs existieren weiter, zeigen aber auf ein anderes
Control). Deshalb laeuft die Ersetzung in EINEM Durchgang ueber die ganze Tabelle, nie als
Folge einzelner Suchen-und-Ersetzen-Schritte (DET.3.1.7 -> DET.3.1.1 waehrend
DET.3.1.1 -> DET.3.2.1).

Idempotenz- und Quellversions-Absicherung:
  Ein zweiter Lauf auf einer bereits migrierten Datei wuerde wiederverwendete IDs erneut
  permutieren (DET.3.1.7 -> DET.3.1.1 -> DET.3.2.1). Deshalb prueft `apply` vor jedem
  Schreibvorgang in Phase 1 fuer alle Zieldateien den tatsaechlichen Katalog-Quellstand
  gegen `meta.katalog_alt_commit` / `meta.katalog_neu_commit` (sowie optional
  `katalog_alt_sha256` / `katalog_neu_sha256`) aus der Move-Tabelle:
  - Nur Dateien mit eindeutig erkanntem Quellstand (`katalog_alt_commit` / `alt_sha256`)
    werden umgeschrieben; dabei werden die Katalog-Pins in derselben Datei auf den
    Zielstand (`katalog_neu_commit` / `neu_sha256`) aktualisiert.
  - Bereits migrierte Dateien (Zielstand schon erreicht), gemischte Staende (Alt + Neu
    oder mehrere Commits), unerwartete Commits oder Dateien ohne erkennbaren Quellstand
    werden strikt abgelehnt (fail closed: Exit-Code 1, nichts wird geschrieben), ausser
    `--force` wird explizit gesetzt.

Zwei Unterbefehle:

  derive  --alt <katalog-alt.json> --neu <katalog-neu.json> --alt-commit SHA --neu-commit SHA
          -o <moves.json>
      Vergleicht beide Staende ueber `alt-identifier` (Controls und Parameter) und schreibt
      die Tabelle: controls {alt: neu}, params {alt: neu}, Commit- und SHA-256-Pins in
      `meta`, dazu neue Controls, entfallene UUIDs und Controls mit geaendertem
      Titel/Statement bei gleichbleibender UUID.

  apply   --moves <moves.json> [--dry-run] [--force] <datei-oder-verzeichnis> ...
      Prueft den Quellstand jeder Zieldatei, ersetzt in Textdateien (*.json, *.md, *.txt,
      *.py, *.csv) alle Vorkommen der alten IDs in einem Durchgang als Token (Control-IDs
      und Parameter-IDs) und aktualisiert erkannte Katalog-Pins auf den Zielstand. Nur
      stdlib.

Selbstpruefung von `apply`: nach dem Lauf enthaelt keine bearbeitete Datei mehr eine der
ENTFALLENEN alten IDs; ausserdem muss der erkannte Dateistand (ausser bei `--force` auf
pinlosen Dateien) dem Zielstand entsprechen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".csv"}

# Contexts in which catalog commit hashes appear across profiles, hilfsdateien, and scripts.
_PIN_CONTEXT_PATTERNS = (
    re.compile(r"Stand-der-Technik-Bibliothek/([0-9a-fA-F]{7,40})(?=/|\"|'|\s|$)"),
    re.compile(
        r'"(?:gpp_pin|katalog_commit|catalog_commit|gpp_catalog_commit|remap_target_commit)"'
        r'\s*:\s*"([0-9a-fA-F]{7,40})"'
    ),
    re.compile(r"(?:@|\bPin|\bCommit)\s+([0-9a-fA-F]{7,40})(?![0-9a-fA-F])"),
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit_matches(found: str, expected: str) -> bool:
    """True when two hex commit references agree on their shared prefix (at least 7 chars)."""
    f_low = found.lower()
    e_low = expected.lower()
    if len(f_low) < 7 or len(e_low) < 7:
        return False
    return e_low.startswith(f_low) or f_low.startswith(e_low)


def _extract_version_pins(
    text: str,
    alt_commit: str,
    neu_commit: str,
    alt_sha256: str = "",
    neu_sha256: str = "",
) -> tuple[set[str], set[str], set[str]]:
    """Extracts source hits, target hits, and unexpected commit pins from `text`."""
    alt_hits: set[str] = set()
    neu_hits: set[str] = set()
    other_commits: set[str] = set()

    for pat in _PIN_CONTEXT_PATTERNS:
        for m in pat.finditer(text):
            commit = m.group(1).lower()
            is_alt = _commit_matches(commit, alt_commit)
            is_neu = _commit_matches(commit, neu_commit)
            if is_alt and not is_neu:
                alt_hits.add(commit)
            elif is_neu and not is_alt:
                neu_hits.add(commit)
            elif is_alt and is_neu:
                other_commits.add(commit)
            else:
                other_commits.add(commit)

    # Also recognize direct full-commit or 12-char pin tokens (and optional SHA-256 digests)
    # even outside the structured URL/JSON contexts above.
    for token, bucket in (
        (alt_commit, alt_hits),
        (alt_commit[:12] if len(alt_commit) >= 12 else "", alt_hits),
        (neu_commit, neu_hits),
        (neu_commit[:12] if len(neu_commit) >= 12 else "", neu_hits),
        (alt_sha256, alt_hits),
        (neu_sha256, neu_hits),
    ):
        if not token or len(token) < 7:
            continue
        if re.search(rf"(?<![0-9a-fA-F]){re.escape(token)}(?![0-9a-fA-F])", text, re.IGNORECASE):
            bucket.add(token.lower())

    return alt_hits, neu_hits, other_commits


def detect_file_version(
    text: str,
    alt_commit: str,
    neu_commit: str,
    alt_sha256: str = "",
    neu_sha256: str = "",
) -> tuple[str, list[str]]:
    """Classifies a file's catalog version against the move table's source/target pins.

    Returns `(status, details)` with status in:
      - 'source': exclusively matches `alt_commit` / `alt_sha256`
      - 'already_migrated': exclusively matches `neu_commit` / `neu_sha256`
      - 'mixed': contains both source and target markers, or source/target plus another commit
      - 'unexpected': contains only commit pin(s) that match neither source nor target
      - 'unknown': contains no recognizable catalog commit or hash marker
    """
    alt_hits, neu_hits, other_commits = _extract_version_pins(
        text, alt_commit, neu_commit, alt_sha256, neu_sha256
    )
    if alt_hits and (neu_hits or other_commits):
        return "mixed", sorted(alt_hits | neu_hits | other_commits)
    if neu_hits and other_commits:
        return "mixed", sorted(neu_hits | other_commits)
    if alt_hits:
        return "source", sorted(alt_hits)
    if neu_hits:
        return "already_migrated", sorted(neu_hits)
    if other_commits:
        return "unexpected", sorted(other_commits)
    return "unknown", []


def update_version_pins(
    text: str,
    alt_commit: str,
    neu_commit: str,
    alt_sha256: str = "",
    neu_sha256: str = "",
) -> tuple[str, int]:
    """Rewrites recognized source commit/hash pins to the target commit/hash."""
    count = 0

    def _replace_token(src: str, dst: str, content: str) -> tuple[str, int]:
        if not src or not dst or src.lower() == dst.lower():
            return content, 0
        pat = re.compile(rf"(?<![0-9a-fA-F]){re.escape(src)}(?![0-9a-fA-F])", re.IGNORECASE)
        return pat.subn(dst, content)

    # Full commit and SHA-256 first, then 12-char pin prefix, then shorter pins in pin contexts.
    text, n = _replace_token(alt_commit, neu_commit, text)
    count += n
    if alt_sha256 and neu_sha256:
        text, n = _replace_token(alt_sha256, neu_sha256, text)
        count += n
    if len(alt_commit) >= 12 and len(neu_commit) >= 12:
        text, n = _replace_token(alt_commit[:12], neu_commit[:12], text)
        count += n

    for pat in _PIN_CONTEXT_PATTERNS:
        def _sub_ctx(m: re.Match) -> str:
            nonlocal count
            found = m.group(1)
            if _commit_matches(found, alt_commit) and not _commit_matches(found, neu_commit):
                replacement = neu_commit[: len(found)] if len(found) < len(neu_commit) else neu_commit
                count += 1
                start, end = m.span(1)
                whole_start = m.start(0)
                return m.group(0)[: start - whole_start] + replacement + m.group(0)[end - whole_start :]
            return m.group(0)

        text = pat.sub(_sub_ctx, text)

    return text, count


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
    alt_sha256 = _sha256_file(args.alt)
    neu_sha256 = _sha256_file(args.neu)
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
            "katalog_alt_sha256": alt_sha256,
            "katalog_neu_sha256": neu_sha256,
            "anzahl_verschoben": len(controls),
            "anzahl_parameter": len(params),
            "anzahl_neu": len(new_controls),
            "anzahl_geaendert_gleiche_uuid": len(changed),
            "hinweis": "controls und params in EINEM Durchgang anwenden (apply); wiederverwendete IDs duerfen nie ein zweites Mal angewendet werden.",
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


def iter_files(paths) -> list[tuple[Path, bool]]:
    """Returns `(file_path, is_explicit)` pairs for all target files."""
    files: list[tuple[Path, bool]] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES:
                    files.append((f, False))
        elif p.is_file():
            files.append((p, True))
        else:
            print(f"WARNUNG: {p} nicht gefunden", file=sys.stderr)
    return files


def _validate_moves_meta(moves: dict) -> tuple[str, str, str, str]:
    """Validates mandatory source and target catalog pins in `moves['meta']`."""
    meta = moves.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Move-Tabelle enthaelt kein 'meta'-Objekt.")
    alt_commit = str(meta.get("katalog_alt_commit") or "").strip()
    neu_commit = str(meta.get("katalog_neu_commit") or "").strip()
    if len(alt_commit) < 7 or len(neu_commit) < 7:
        raise ValueError(
            "Move-Tabelle muss 'meta.katalog_alt_commit' und 'meta.katalog_neu_commit' "
            "(mindestens 7 Zeichen) enthalten."
        )
    if _commit_matches(alt_commit, neu_commit):
        raise ValueError(
            f"Quell- und Ziel-Commit in Move-Tabelle sind identisch/mehrdeutig: "
            f"alt={alt_commit!r}, neu={neu_commit!r}."
        )
    alt_sha256 = str(meta.get("katalog_alt_sha256") or "").strip()
    neu_sha256 = str(meta.get("katalog_neu_sha256") or "").strip()
    return alt_commit, neu_commit, alt_sha256, neu_sha256


def apply(args) -> int:
    moves = json.loads(args.moves.read_text(encoding="utf-8"))
    try:
        alt_commit, neu_commit, alt_sha256, neu_sha256 = _validate_moves_meta(moves)
    except ValueError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    controls = dict(moves["controls"])
    params = dict(moves.get("params", {}))
    # Parameter-IDs, die nur aus der Control-Verschiebung folgen, aber im Katalog keine eigene
    # alt-identifier tragen, werden aus den Control-Moves erzeugt (det.3.1.7-prm1 -> det.3.1.1-prm1).
    for a, b in controls.items():
        params.setdefault(a.lower(), b.lower())
    # Die Parameter-Tabelle enthaelt dann auch Eintraege ohne `-prm`; der Token-Lookahead
    # (kein Buchstabe/keine Ziffer danach) laesst `det.3.3` vor `-prm1` zu und verhindert
    # Treffer mitten in Woertern.
    removed = set(moves.get("entfallene_uuids", [])) | (set(controls) - set(controls.values()))
    removed_check = build_pattern({i: i for i in removed})
    force = bool(getattr(args, "force", False))

    # Phase 1: Validate every candidate file BEFORE writing anything (fail closed).
    planned: list[tuple[Path, str, int, int, str]] = []
    errors: list[str] = []

    for f, is_explicit in iter_files(args.paths):
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        status, details = detect_file_version(text, alt_commit, neu_commit, alt_sha256, neu_sha256)
        remapped_text, id_hits = remap_text(text, controls, params)
        new_text, pin_hits = update_version_pins(remapped_text, alt_commit, neu_commit, alt_sha256, neu_sha256)

        if status != "source":
            # In directory scans, ignore completely unrelated files with neither pins nor ID hits.
            if not is_explicit and status == "unknown" and id_hits == 0 and pin_hits == 0:
                continue

            reason_map = {
                "already_migrated": (
                    f"bereits auf Zielstand {neu_commit} migriert (gefunden: {', '.join(details)})"
                ),
                "mixed": (
                    f"gemischter/widerspruechlicher Katalogstand (gefunden: {', '.join(details)})"
                ),
                "unexpected": (
                    f"unerwarteter Quellstand (erwartet: {alt_commit}, gefunden: {', '.join(details)})"
                ),
                "unknown": (
                    f"kein Katalog-Quellstand ({alt_commit}) erkennbar"
                ),
            }
            msg = f"{f}: {reason_map[status]}"
            if not force:
                errors.append(msg)
                continue
            print(f"WARNUNG (--force): {msg}", file=sys.stderr)

        if id_hits == 0 and pin_hits == 0:
            continue
        planned.append((f, new_text, id_hits, pin_hits, status))

    if errors:
        print(
            "ABBRUCH: Quellversions-Pruefung fehlgeschlagen — keine Datei wurde veraendert "
            "(zum bewussten Ueberschreiben --force verwenden):",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  FEHLER: {err}", file=sys.stderr)
        return 1

    # Phase 2: Write validated files and run post-write integrity checks.
    total_files = total_hits = total_pins = 0
    for f, new_text, id_hits, pin_hits, orig_status in planned:
        total_files += 1
        total_hits += id_hits
        total_pins += pin_hits
        print(f"  {id_hits:5d} IDs, {pin_hits:2d} Pins  {f}")
        if not args.dry_run:
            f.write_text(new_text, encoding="utf-8", newline="")
            if removed_check and removed_check.search(new_text):
                print(f"FEHLER: {f} enthaelt nach dem Lauf noch eine entfallene ID", file=sys.stderr)
                return 1
            if orig_status == "source":
                post_status, post_details = detect_file_version(
                    new_text, alt_commit, neu_commit, alt_sha256, neu_sha256
                )
                if post_status != "already_migrated":
                    print(
                        f"FEHLER: {f} zeigt nach dem Lauf keinen sauberen Zielstand "
                        f"(Status={post_status}, Pins={post_details})",
                        file=sys.stderr,
                    )
                    return 1

    print(
        f"{'(dry-run) ' if args.dry_run else ''}{total_hits} ID-Ersetzungen und "
        f"{total_pins} Pin-Aktualisierungen in {total_files} Dateien."
    )
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
    a.add_argument(
        "--force",
        action="store_true",
        help="Quellversions-Pruefung uebersteuern (erlaubt Anwendung auf Dateien ohne/mit abweichendem Pin)",
    )
    a.add_argument("paths", nargs="+")
    a.set_defaults(func=apply)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
