"""part_classes.json stays in sync with the manual tables and the goBILDA catalog."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_part_classes", REPO / "scripts" / "kb" / "build_part_classes.py"
)
bpc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bpc)

ADDON = REPO / "addon" / "server"
PARTS = REPO / "kb" / "parts" / "parts.csv"


def _rows():
    with PARTS.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.skipif(not PARTS.exists(), reason="goBILDA catalog not present")
def test_committed_table_is_up_to_date():
    current = json.loads((ADDON / "part_classes.json").read_text())
    assert bpc.build(current, _rows()) == current, (
        "Run: python3 -I scripts/kb/build_part_classes.py"
    )


@pytest.mark.skipif(not PARTS.exists(), reason="goBILDA catalog not present")
def test_every_catalog_motor_and_servo_classifies_by_sku():
    import sys

    sys.path.insert(0, str(ADDON))
    import assembly_math as asm

    wrong = [
        (r["sku"], r["counts_as"], asm.classify_part(r["sku"], ""))
        for r in _rows()
        if (r["counts_as"] if r["counts_as"] in ("motor", "servo") else None)
        != asm.classify_part(r["sku"], "")
    ]
    assert wrong == []


def test_build_keeps_hand_entries_and_drops_redundant_ones():
    current = {
        "_comment": "x",
        "motor": ["REV-41-1600", "5203-2402-0019"],
        "servo": [],
        "_names": {"motor": ["motor"]},
    }
    rows = [
        {"sku": "5303-2402-0001", "counts_as": "motor"},
        {"sku": "5303-2402-0002", "counts_as": "motor"},
        {"sku": "3215-0001-0002", "counts_as": "servo"},
        {"sku": "3215-0001-0099", "counts_as": "none"},  # mixed series → exact SKU
        {"sku": "1120-0001-0336", "counts_as": "none"},
    ]
    out = bpc.build(current, rows)
    assert "REV-41-1600" in out["motor"]  # hand entry kept
    assert "5203-2402-0019" not in out["motor"]  # covered by the manual's 5203-
    assert "5303-2402-" in out["motor"]  # whole series is motors
    assert "3215-0001-0002" in out["servo"]  # series is mixed, so exact SKU
    assert not any(p.startswith("1120") for p in out["motor"] + out["servo"])
    assert out["_names"] == {"motor": ["motor"]}
    assert list(out)[:3] == ["_comment", "motor", "servo"]
