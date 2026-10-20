"""Tests for the pure helpers behind check_robot_rules."""

import json
import sys
from pathlib import Path

import pytest

ADDON_SERVER = Path(__file__).resolve().parents[1] / "addon" / "server"
sys.path.insert(0, str(ADDON_SERVER))

import robot_rules as rr  # noqa: E402

CONSTRAINTS = {
    "season": "2026-27",
    "starting_size": {"rule": "R102", "box": [45.7, 45.7, 45.7]},
    "expansion_size": {
        "rule": "R105",
        "box": [45.7, 61.0, 73.65],
        "vertical_axis_is": 73.65,
    },
    "actuators": {
        "max_motors": {"rule": "R503", "count": 8},
        "max_servos": {"count": 8},
    },
}


class TestLoad:
    def test_latest_season_wins(self, tmp_path):
        for season, game in (("2025-26", "old"), ("2026-27", "new")):
            (tmp_path / season).mkdir()
            (tmp_path / season / "constraints.json").write_text(
                json.dumps({"game": game})
            )
        assert rr.load_constraints(str(tmp_path))["game"] == "new"

    def test_missing_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="constraints.json"):
            rr.load_constraints(str(tmp_path))

    def test_limits_from(self):
        lim = rr.limits_from(CONSTRAINTS)
        assert lim["starting_box"] == [45.7, 45.7, 45.7]
        assert lim["expansion_vertical"] == 73.65
        assert (lim["max_motors"], lim["max_servos"]) == (8, 8)


class TestFitsBox:
    def test_cube_any_orientation(self):
        assert rr.fits_box([45, 40, 30], [45.7] * 3, "z", None)["ok"]
        res = rr.fits_box([46.7, 40, 30], [45.7] * 3, "z", None)
        assert not res["ok"] and res["over_cm"] == 1.0

    def test_vertical_axis_is_held(self):
        box = [45.7, 61.0, 73.65]
        # 70 cm tall robot: fits only with z up
        assert rr.fits_box([40, 60, 70], box, "z", 73.65)["ok"]
        assert not rr.fits_box([40, 60, 70], box, "y", 73.65)["ok"]

    def test_horizontal_yaw_is_free(self):
        assert rr.fits_box([60, 45, 10], [45.7, 61.0, 73.65], "z", 73.65)["ok"]


class TestEnvelope:
    def test_inside(self):
        env = {"min": [0, 0, 0], "max": [10, 10, 10]}
        assert rr.envelope_check(([1, 1, 1], [9, 9, 9]), env) == {
            "ok": True,
            "over_cm": {},
        }

    def test_overhang_per_axis(self):
        env = {"min": [0, 0, 0], "max": [10, 10, 10]}
        res = rr.envelope_check(([-2, 1, 1], [9, 9, 10.5]), env)
        assert res == {"ok": False, "over_cm": {"x": 2, "z": 0.5}}


def test_count_check():
    rows = rr.count_check({"motor": 3, "servo": 1}, {"motors": 2, "servos": 2})
    assert [r["ok"] for r in rows] == [False, True]
    assert rows[0]["value"] == 3


def test_boxes_overlap():
    a = ([0, 0, 0], [1, 1, 1])
    assert rr.boxes_overlap(a, ([1, 0, 0], [2, 1, 1]))  # touching counts
    assert not rr.boxes_overlap(a, ([1.1, 0, 0], [2, 1, 1]))


def test_repo_constraints_load_if_present():
    path = Path(rr.kb_rules_dir())
    if not list(path.glob("*/constraints.json")):
        pytest.skip("no kb rules in this checkout")
    lim = rr.limits_from(rr.load_constraints())
    assert lim["max_motors"] and lim["starting_box"]
