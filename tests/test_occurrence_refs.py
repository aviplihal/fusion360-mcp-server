"""Tests for occurrence lookup and face/edge refs.

``addon/server/occurrence_refs.py`` is loaded by path: the addon package
imports Fusion's ``adsk`` runtime, which isn't installable here, but this
module deliberately has no such dependency.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ADDON_SERVER = Path(__file__).resolve().parent.parent / "addon" / "server"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


refs = _load(ADDON_SERVER / "occurrence_refs.py", "occurrence_refs")

ROWS = [
    ("Plate:1", "Plate"),
    ("Channel:1", "Channel"),
    ("Channel:2", "Channel"),
    ("Drivetrain:1", "Drivetrain"),
    ("Drivetrain:1+Motor:1", "Motor"),
]


class TestPickOccurrence:
    def test_full_path(self):
        assert refs.pick_occurrence("Drivetrain:1+Motor:1", ROWS) == 4

    def test_occurrence_name(self):
        assert refs.pick_occurrence("Channel:2", ROWS) == 2

    def test_leaf_name_of_nested_occurrence(self):
        assert refs.pick_occurrence("Motor:1", ROWS) == 4

    def test_unique_component_name(self):
        assert refs.pick_occurrence("Plate", ROWS) == 0

    def test_shared_component_name_is_ambiguous(self):
        with pytest.raises(RuntimeError, match="matches 2 occurrences") as exc:
            refs.pick_occurrence("Channel", ROWS)
        assert "Channel:1, Channel:2" in str(exc.value)

    def test_same_leaf_in_two_subassemblies_is_ambiguous(self):
        rows = [("Left:1+Wheel:1", "Wheel"), ("Right:1+Wheel:1", "Wheel")]
        with pytest.raises(RuntimeError, match="Left:1\\+Wheel:1, Right:1\\+Wheel:1"):
            refs.pick_occurrence("Wheel:1", rows)

    def test_not_found(self):
        with pytest.raises(RuntimeError, match="not found"):
            refs.pick_occurrence("Servo", ROWS)

    def test_long_candidate_list_is_elided(self):
        rows = [(f"Screw:{i}", "Screw") for i in range(1, 21)]
        with pytest.raises(RuntimeError, match="matches 20 occurrences") as exc:
            refs.pick_occurrence("Screw", rows)
        assert "Screw:9" not in str(exc.value)
        assert "…" in str(exc.value)


class TestRefs:
    def test_parse_face(self):
        assert refs.parse_ref("Channel:2/b0/f37") == ("Channel:2", 0, "face", 37)

    def test_parse_edge_nested(self):
        assert refs.parse_ref("A:1+B:2/b1/e5") == ("A:1+B:2", 1, "edge", 5)

    def test_parse_root_body(self):
        assert refs.parse_ref("/b0/f3") == ("", 0, "face", 3)

    @pytest.mark.parametrize("bad", ["Channel:2", "Channel:2/f37", "X/b0/v1", ""])
    def test_parse_bad(self, bad):
        with pytest.raises(RuntimeError, match="Bad ref"):
            refs.parse_ref(bad)

    def test_round_trip(self):
        ref = refs.make_ref("Channel:2", 0, "face", 37)
        assert refs.parse_ref(ref) == ("Channel:2", 0, "face", 37)


class TestUnionBbox:
    def test_empty(self):
        assert refs.union_bbox([]) is None

    def test_union(self):
        boxes = [([0, 0, 0], [4, 2, 0.5]), ([20, -1, 0], [24, 1, 3])]
        assert refs.union_bbox(boxes) == ([0, -1, 0], [24, 2, 3])


class TestBoxContains:
    BODY = ([0, 0, 0], [4, 2, 0.5])

    def test_overlap_region_inside(self):
        assert refs.box_contains(self.BODY, ([1, 0, 0], [4, 2, 0.5]))

    def test_zero_thickness_on_face(self):
        # Coincident faces produce a zero-thickness interference region.
        assert refs.box_contains(self.BODY, ([4, 0, 0], [4, 2, 0.5]))

    def test_neighbour_that_only_touches(self):
        # Region past the body's max x: a touching neighbour, not a party.
        assert not refs.box_contains(self.BODY, ([3.98, 0, 0], [4.02, 2, 0.5]))

    def test_apart(self):
        assert not refs.box_contains(self.BODY, ([0, 0, 10], [4, 2, 10.5]))
