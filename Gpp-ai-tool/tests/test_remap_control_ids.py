"""Offline regression tests for scripts/remap_control_ids.py (#7 idempotency & source-version guard)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "remap_control_ids.py"
_SPEC = importlib.util.spec_from_file_location("remap_control_ids", SCRIPT_PATH)
remap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(remap)

ALT_COMMIT = "160c177d4f2a8b901234567890abcdef12345678"
NEU_COMMIT = "dc44ea4987654321fedcba098765432109876543"
OTHER_COMMIT = "deadbeefcafebabe111122223333444455556666"


def _write_moves(tmp_path: Path, *, alt_commit=ALT_COMMIT, neu_commit=NEU_COMMIT) -> Path:
    moves = {
        "meta": {
            "katalog_alt_commit": alt_commit,
            "katalog_neu_commit": neu_commit,
        },
        "controls": {
            "DET.3.1.7": "DET.3.1.1",
            "DET.3.1.1": "DET.3.2.1",
            "DET.3.9.9": "DET.3.8.1",
        },
        "params": {
            "det.3.1.7-prm1": "det.3.1.1-prm1",
            "det.3.1.1-prm1": "det.3.2.1-prm1",
        },
        "entfallene_uuids": [],
    }
    p = tmp_path / "moves.json"
    p.write_text(json.dumps(moves), encoding="utf-8")
    return p


def _source_profile_text(commit: str = ALT_COMMIT) -> str:
    return json.dumps(
        {
            "profile": {
                "imports": [
                    {
                        "href": f"https://raw.githubusercontent.com/BSI/Stand-der-Technik-Bibliothek/{commit}/catalog.json",
                        "include-controls": [{"with-ids": ["DET.3.1.7", "DET.3.1.1"]}],
                    }
                ],
                "modify": {"set-parameters": [{"param-id": "det.3.1.7-prm1", "values": ["x"]}]},
            }
        },
        indent=2,
    )


def test_apply_migrates_once_and_rejects_second_run_on_reused_ids(tmp_path, capsys):
    moves = _write_moves(tmp_path)
    target = tmp_path / "profile.json"
    target.write_text(_source_profile_text(ALT_COMMIT), encoding="utf-8")

    # First run: succeeds, remaps chain in one pass (DET.3.1.7 -> DET.3.1.1, DET.3.1.1 -> DET.3.2.1)
    # and updates the catalog commit pin from ALT_COMMIT -> NEU_COMMIT.
    assert remap.main(["apply", "--moves", str(moves), str(target)]) == 0
    migrated = target.read_text(encoding="utf-8")
    doc = json.loads(migrated)
    assert doc["profile"]["imports"][0]["include-controls"][0]["with-ids"] == ["DET.3.1.1", "DET.3.2.1"]
    assert doc["profile"]["modify"]["set-parameters"][0]["param-id"] == "det.3.1.1-prm1"
    assert NEU_COMMIT in doc["profile"]["imports"][0]["href"]
    assert ALT_COMMIT not in migrated

    # Second run on the SAME file: MUST fail closed (exit 1) and NOT permute DET.3.1.1 -> DET.3.2.1!
    rc = remap.main(["apply", "--moves", str(moves), str(target)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "bereits auf Zielstand" in err
    assert target.read_text(encoding="utf-8") == migrated


def test_apply_rejects_mixed_unexpected_and_unknown_source_versions(tmp_path, capsys):
    moves = _write_moves(tmp_path)

    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        f'{{"gpp_pin": "{ALT_COMMIT}", "other": "Stand-der-Technik-Bibliothek/{NEU_COMMIT}/c.json", "id": "DET.3.1.7"}}',
        encoding="utf-8",
    )
    mixed_orig = mixed.read_text(encoding="utf-8")
    assert remap.main(["apply", "--moves", str(moves), str(mixed)]) == 1
    assert "gemischter" in capsys.readouterr().err
    assert mixed.read_text(encoding="utf-8") == mixed_orig

    unexpected = tmp_path / "unexpected.json"
    unexpected.write_text(_source_profile_text(OTHER_COMMIT), encoding="utf-8")
    unexpected_orig = unexpected.read_text(encoding="utf-8")
    assert remap.main(["apply", "--moves", str(moves), str(unexpected)]) == 1
    assert "unerwarteter Quellstand" in capsys.readouterr().err
    assert unexpected.read_text(encoding="utf-8") == unexpected_orig

    unknown = tmp_path / "unknown.json"
    unknown.write_text('{"ids": ["DET.3.1.7"]}', encoding="utf-8")
    unknown_orig = unknown.read_text(encoding="utf-8")
    assert remap.main(["apply", "--moves", str(moves), str(unknown)]) == 1
    assert "kein Katalog-Quellstand" in capsys.readouterr().err
    assert unknown.read_text(encoding="utf-8") == unknown_orig


def test_apply_is_two_phase_atomic_and_supports_explicit_force(tmp_path, capsys):
    moves = _write_moves(tmp_path)
    good = tmp_path / "good.json"
    already = tmp_path / "already.json"
    good.write_text(_source_profile_text(ALT_COMMIT), encoding="utf-8")
    already.write_text(_source_profile_text(NEU_COMMIT), encoding="utf-8")
    good_orig = good.read_text(encoding="utf-8")

    # One invalid file in the batch must prevent writing ANY file.
    assert remap.main(["apply", "--moves", str(moves), str(good), str(already)]) == 1
    assert good.read_text(encoding="utf-8") == good_orig

    # Explicit --force overrides the version guard on a pinless file.
    pinless = tmp_path / "pinless.json"
    pinless.write_text('{"ids": ["DET.3.1.7"]}', encoding="utf-8")
    assert remap.main(["apply", "--moves", str(moves), "--force", str(pinless)]) == 0
    assert json.loads(pinless.read_text(encoding="utf-8"))["ids"] == ["DET.3.1.1"]


def test_apply_fails_closed_when_moves_meta_commits_missing_or_identical(tmp_path, capsys):
    target = tmp_path / "profile.json"
    target.write_text(_source_profile_text(ALT_COMMIT), encoding="utf-8")

    bad_missing = _write_moves(tmp_path, alt_commit="", neu_commit=NEU_COMMIT)
    assert remap.main(["apply", "--moves", str(bad_missing), str(target)]) == 1
    assert "katalog_alt_commit" in capsys.readouterr().err

    bad_same = _write_moves(tmp_path, alt_commit=ALT_COMMIT, neu_commit=ALT_COMMIT)
    assert remap.main(["apply", "--moves", str(bad_same), str(target)]) == 1
    assert "identisch" in capsys.readouterr().err


def test_derive_records_commit_and_sha256_pins(tmp_path):
    alt_cat = {
        "catalog": {
            "controls": [
                {"id": "DET.3.1.7", "title": "A", "props": [{"name": "alt-identifier", "value": "uuid-1"}]},
                {"id": "DET.3.1.1", "title": "B", "props": [{"name": "alt-identifier", "value": "uuid-2"}]},
            ]
        }
    }
    neu_cat = {
        "catalog": {
            "controls": [
                {"id": "DET.3.1.1", "title": "A", "props": [{"name": "alt-identifier", "value": "uuid-1"}]},
                {"id": "DET.3.2.1", "title": "B", "props": [{"name": "alt-identifier", "value": "uuid-2"}]},
            ]
        }
    }
    alt_p = tmp_path / "alt.json"
    neu_p = tmp_path / "neu.json"
    out_p = tmp_path / "moves.json"
    alt_p.write_text(json.dumps(alt_cat), encoding="utf-8")
    neu_p.write_text(json.dumps(neu_cat), encoding="utf-8")

    assert remap.main(
        ["derive", "--alt", str(alt_p), "--neu", str(neu_p), "--alt-commit", ALT_COMMIT, "--neu-commit", NEU_COMMIT, "-o", str(out_p)]
    ) == 0
    doc = json.loads(out_p.read_text(encoding="utf-8"))
    assert doc["meta"]["katalog_alt_commit"] == ALT_COMMIT
    assert doc["meta"]["katalog_neu_commit"] == NEU_COMMIT
    assert len(doc["meta"]["katalog_alt_sha256"]) == 64
    assert len(doc["meta"]["katalog_neu_sha256"]) == 64
    assert doc["controls"] == {"DET.3.1.1": "DET.3.2.1", "DET.3.1.7": "DET.3.1.1"}
