"""Tests for the pure helpers behind set_joint_value and get_timeline.

``joint_values.py`` and ``timeline_rows.py`` are loaded by path: the addon
package imports Fusion's ``adsk`` runtime, but these modules don't.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

ADDON_SERVER = Path(__file__).resolve().parent.parent / "addon" / "server"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


jv = _load(ADDON_SERVER / "joint_values.py", "joint_values")
tl = _load(ADDON_SERVER / "timeline_rows.py", "timeline_rows")


# ── joint values ──────────────────────────────────────────────────────


def test_joint_type_name():
    assert jv.joint_type_name(1) == "revolute"
    assert jv.joint_type_name(4) == "pin_slot"
    assert jv.joint_type_name(7) == "7"  # InferredJointType


def test_unit_conversion_round_trips():
    assert jv.to_api(180, "deg") == pytest.approx(math.pi)
    assert jv.to_api(2.5, "cm") == 2.5
    assert jv.from_api(math.pi / 2, "deg") == 90.0
    assert jv.from_api(1.23456, "cm") == 1.2346


def test_plan_revolute():
    assert jv.plan("revolute", value=90) == [("rotation", "deg", 90, None)]


def test_plan_two_values():
    steps = jv.plan("cylindrical", value=30, value2=2, limits2={"min": 0})
    assert steps == [
        ("rotation", "deg", 30, None),
        ("slide", "cm", 2, {"min": 0}),
    ]
    # Only the second motion touched.
    assert jv.plan("pin_slot", value2=1) == [("slide", "cm", 1, None)]


def test_plan_rejects_bad_requests():
    with pytest.raises(RuntimeError, match="no settable value"):
        jv.plan("rigid", value=1)
    with pytest.raises(RuntimeError, match="Pass value"):
        jv.plan("revolute")
    with pytest.raises(RuntimeError, match="one value"):
        jv.plan("slider", value=1, value2=2)
    with pytest.raises(RuntimeError, match="Unknown limits keys"):
        jv.plan("revolute", limits={"lo": 1})
    with pytest.raises(RuntimeError, match="greater than max"):
        jv.plan("revolute", limits={"min": 10, "max": 5})


def test_limit_updates():
    ups = jv.limit_updates({"min": -90, "rest": None}, "deg")
    assert ups[0][0:2] == ("Minimum", True)
    assert ups[0][2] == pytest.approx(-math.pi / 2)
    assert ups[1] == ("Rest", False, None)


def test_limits_dict_reports_enabled_only():
    enabled = {"min": True, "max": False, "rest": True}
    values = {"min": -math.pi / 4, "max": 1.0, "rest": 0.0}
    assert jv.limits_dict(enabled, values, "deg") == {"min": -45.0, "rest": 0.0}
    assert jv.limits_dict({}, values, "cm") is None


# ── timeline rows ─────────────────────────────────────────────────────


def test_short_type():
    assert tl.short_type("adsk::fusion::ExtrudeFeature") == "Extrude"
    assert tl.short_type("adsk::fusion::Occurrence") == "Occurrence"
    assert tl.short_type(None) == "?"


def test_row_strips_name_and_adds_message_only_when_unhealthy():
    ok = tl.row(0, " Part:1", "adsk::fusion::Occurrence", False, 0, "ignored")
    assert ok == {
        "i": 0,
        "name": "Part:1",
        "type": "Occurrence",
        "suppressed": False,
        "health": "healthy",
    }
    bad = tl.row(3, "Fillet1", "adsk::fusion::FilletFeature", False, 2, "Boom\nmore")
    assert bad["health"] == "error"
    assert bad["message"] == "Boom"
    assert tl.row(4, "x", None, True, 3)["health"] == "suppressed"


def test_group_row_takes_worst_child():
    kids = [
        tl.row(1, "Sketch1", "adsk::fusion::Sketch", False, 0),
        tl.row(1, "Extrude1", "adsk::fusion::ExtrudeFeature", False, 1, "warn"),
    ]
    g = tl.group_row(1, "Group1", False, kids)
    assert g["health"] == "warning"
    assert g["items"] == 2
    assert [c["name"] for c in g["issues"]] == ["Extrude1"]
    clean = tl.group_row(2, "G", False, kids[:1])
    assert clean["health"] == "healthy"
    assert "issues" not in clean


def test_page():
    rows = [tl.row(i, f"F{i}", None, False, 2 if i == 3 else 0) for i in range(6)]
    sel, n = tl.page(rows, offset=2, limit=2)
    assert [r["i"] for r in sel] == [2, 3]
    assert n == 6
    sel, n = tl.page(rows, errors_only=True)
    assert [r["i"] for r in sel] == [3]
    assert n == 1
