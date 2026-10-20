"""Tests for join_on_holes side picking, matrix decoding and part classes.

``addon/server/assembly_math.py`` is loaded by path because the addon
package imports Fusion's ``adsk`` runtime; this module doesn't.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

ADDON_SERVER = Path(__file__).resolve().parent.parent / "addon" / "server"
_spec = importlib.util.spec_from_file_location(
    "assembly_math", ADDON_SERVER / "assembly_math.py"
)
asm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(asm)

# Values from the live test: a 0.3175 cm plate at x 20.32..20.6375, hole axis
# along -x (start on the +x face).
PLATE_BOX = ([20.32, -21.91, 0.7], [20.6375, 16.51, 19.9])
PLATE_HOLE = ([20.6375, -6.44, 5.88], [20.32, -6.44, 5.88])
# A flat 6 x 1.6 x 0.3 bracket lying at z 30..30.3, hole along -z.
BRACKET_BOX = ([0.0, 0.0, 30.0], [6.0, 1.6, 30.3])
BRACKET_HOLE = ([1.4, 0.8, 30.3], [1.4, 0.8, 30.0])


def _box_at(box, dx):
    return ([box[0][0] + dx, *box[0][1:]], [box[1][0] + dx, *box[1][1:]])


class TestPickJoinSides:
    def test_flat_plate_mover_on_end_side(self):
        # Bracket center x=3 is on the plate's end (-x) side.
        s = asm.pick_join_sides(PLATE_HOLE, PLATE_BOX, BRACKET_HOLE, BRACKET_BOX)
        assert s == {
            "fixed": "end",
            "mover": "start",
            "flip": False,
            "reason": "mover position",
        }

    def test_flat_plate_mover_on_start_side(self):
        s = asm.pick_join_sides(
            PLATE_HOLE, PLATE_BOX, BRACKET_HOLE, _box_at(BRACKET_BOX, 40)
        )
        assert (s["fixed"], s["mover"], s["flip"]) == ("start", "end", False)

    def test_channel_bulk_beats_mover_position(self):
        # U-channel x,y 0..4.8, bottom wall y 0..0.25, hole along +y.
        box = ([0, 0, 0], [4.8, 4.8, 10])
        hole = ([2.4, 0.0, 2.0], [2.4, 0.25, 2.0])
        # Mover sits inside the channel's open side, yet must go outside (y<0).
        mover_box = ([0, 10, 30], [6, 11.6, 30.3])
        s = asm.pick_join_sides(hole, box, BRACKET_HOLE, mover_box)
        assert s["fixed"] == "start"
        assert s["reason"] == "fixed part bulk"
        assert s["flip"] is False

    def test_channel_mover_touches_with_outer_face(self):
        # The mover is the channel; its outer end is "start". On the plate's
        # end side the unflipped contact would be "start" too.
        ch_box = ([0, 0, 0], [4.8, 4.8, 10])
        ch_hole = ([2.4, 0.0, 2.0], [2.4, 0.25, 2.0])
        s = asm.pick_join_sides(PLATE_HOLE, PLATE_BOX, ch_hole, ch_box)
        assert (s["fixed"], s["mover"], s["flip"]) == ("end", "start", False)
        # Moved to the start side, the outer end must still touch: flip.
        s = asm.pick_join_sides(PLATE_HOLE, PLATE_BOX, ch_hole, _box_at(ch_box, 40))
        assert (s["fixed"], s["mover"], s["flip"]) == ("start", "start", True)

    def test_reversed_hole_direction_mirrors_choice(self):
        hole = (PLATE_HOLE[1], PLATE_HOLE[0])
        s = asm.pick_join_sides(hole, PLATE_BOX, BRACKET_HOLE, BRACKET_BOX)
        assert s["fixed"] == "start"

    def test_degenerate_hole_defaults_to_start(self):
        p = [1.0, 1.0, 1.0]
        s = asm.pick_join_sides((p, p), PLATE_BOX, (p, p), PLATE_BOX)
        assert s["fixed"] == "start"


def _rot_z(deg):
    a = math.radians(deg)
    return [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]


class TestAxisAngle:
    def test_identity_is_none(self):
        assert asm.axis_angle([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) is None

    @pytest.mark.parametrize("deg", [30, 90, 179])
    def test_about_z(self, deg):
        axis, angle = asm.axis_angle(_rot_z(deg))
        assert angle == pytest.approx(deg)
        assert axis == pytest.approx([0, 0, 1])

    def test_180_about_diagonal(self):
        # 180° about (1, 0, 1)/√2: R = 2uuᵀ − I.
        u = [1 / math.sqrt(2), 0, 1 / math.sqrt(2)]
        r = [[2 * u[i] * u[j] - (i == j) for j in range(3)] for i in range(3)]
        axis, angle = asm.axis_angle(r)
        assert angle == pytest.approx(180)
        assert [abs(a) for a in axis] == pytest.approx([abs(a) for a in u])

    def test_matrix_rows_from_flat(self):
        flat = [1, 2, 3, 10, 4, 5, 6, 20, 7, 8, 9, 30, 0, 0, 0, 1]
        assert asm.matrix_rows(flat) == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]


class TestClassifyPart:
    def test_table_file_is_valid(self):
        data = json.loads((ADDON_SERVER / "part_classes.json").read_text())
        table = asm.part_classes()
        assert set(table) == {"motor", "servo"}
        assert "_comment" in data

    @pytest.mark.parametrize(
        "pn,name,want",
        [
            ("5203-2402-0019", "Motor", "motor"),
            ("", "5202-0002-0139 Yellow Jacket", "motor"),
            ("rev-41-1291", "HD Hex", "motor"),
            ("2000-0025-0002", "Servo", "servo"),
            ("1120-0001-0336", "Channel", None),
            ("", "", None),
        ],
    )
    def test_classify(self, pn, name, want):
        assert asm.classify_part(pn, name) == want

    def test_custom_table(self):
        assert asm.classify_part("X-1", "", {"sensor": ["x-"]}) == "sensor"
