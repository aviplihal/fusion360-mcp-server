"""Pure helpers for the robot-scale assembly tools.

Deliberately free of ``adsk`` imports so the side-picking rule for
``join_on_holes``, matrix decoding for ``list_components`` and part
classification for ``get_bom`` can be unit-tested without Fusion.
"""

from __future__ import annotations

import json
import math
import os

Vec = tuple[float, float, float] | list[float]
Box = tuple[Vec, Vec]


def _sub(a: Vec, b: Vec) -> list[float]:
    return [a[i] - b[i] for i in range(3)]


def _dot(a: Vec, b: Vec) -> float:
    return sum(a[i] * b[i] for i in range(3))


def _center(box: Box) -> list[float]:
    return [(box[0][i] + box[1][i]) / 2 for i in range(3)]


def _extent_along(box: Box, u: Vec) -> float:
    """Length of *box* projected onto unit vector *u*."""
    return sum(abs(u[i]) * (box[1][i] - box[0][i]) for i in range(3))


def _outer_end(start: Vec, end: Vec, box: Box) -> str | None:
    """Which end of a hole faces away from the bulk of its part.

    The bulk is the part's bbox center. Returns None when the part is
    (nearly) symmetric about the hole's mid-plane, as a flat plate or
    bracket is: both ends are then outer faces.
    """
    axis = _sub(end, start)
    length = math.sqrt(_dot(axis, axis))
    if length < 1e-9:
        return None
    u = [a / length for a in axis]
    mid = [(start[i] + end[i]) / 2 for i in range(3)]
    bulk = _dot(_sub(_center(box), mid), u)
    # Below one wall thickness the offset is pockets/countersinks, not bulk.
    if abs(bulk) <= max(length, 0.05 * _extent_along(box, u)):
        return None
    # Bulk lies toward +u (the end side), so the start end faces outward.
    return "start" if bulk > 0 else "end"


def pick_join_sides(
    fixed_hole: tuple[Vec, Vec],
    fixed_box: Box,
    mover_hole: tuple[Vec, Vec],
    mover_box: Box,
) -> dict:
    """Keypoints and flip so the mover lands outside the fixed part.

    *fixed_hole* / *mover_hole* are the ``(start, end)`` points find_holes
    reports; boxes are ``(min, max)``. Returns
    ``{"fixed": "start"|"end", "mover": "start"|"end", "flip": bool,
    "reason": str}``.

    Fusion aligns the two holes' start→end axes. Unflipped, the mover's
    body then extends from its contact keypoint toward its other end, so
    mover ``end`` → fixed ``start`` stacks it on the fixed start side and
    mover ``start`` → fixed ``end`` on the end side (live-tested). When the
    mover must touch with the "wrong" end, flipping reverses its axis.
    """
    fs, fe = fixed_hole
    fixed_side = _outer_end(fs, fe, fixed_box)
    reason = "fixed part bulk"
    if fixed_side is None:
        # Symmetric part: go to whichever side the mover is on now.
        axis = _sub(fe, fs)
        mid = [(fs[i] + fe[i]) / 2 for i in range(3)]
        toward = _dot(_sub(_center(mover_box), mid), axis)
        fixed_side = "end" if toward > 1e-9 else "start"
        reason = "mover position"

    mover_contact = _outer_end(mover_hole[0], mover_hole[1], mover_box)
    if mover_contact is None:
        # Either end is an outer face; pick the one that needs no flip.
        mover_contact = "end" if fixed_side == "start" else "start"
    flip = mover_contact == fixed_side
    return {
        "fixed": fixed_side,
        "mover": mover_contact,
        "flip": flip,
        "reason": reason,
    }


def axis_angle(rows: list[list[float]]) -> tuple[list[float], float] | None:
    """(unit axis, degrees) of a 3×3 rotation matrix; None if identity."""
    r = rows
    trace = r[0][0] + r[1][1] + r[2][2]
    cos_a = max(-1.0, min(1.0, (trace - 1) / 2))
    angle = math.acos(cos_a)
    if angle < 1e-6:
        return None
    if math.pi - angle < 1e-6:
        # 180°: axis from the diagonal (R = 2uuᵀ − I).
        diag = [max(0.0, (r[i][i] + 1) / 2) for i in range(3)]
        k = max(range(3), key=lambda i: diag[i])
        axis = [0.0, 0.0, 0.0]
        axis[k] = math.sqrt(diag[k])
        for i in range(3):
            if i != k:
                axis[i] = (r[k][i] + r[i][k]) / (4 * axis[k])
    else:
        s = 2 * math.sin(angle)
        axis = [
            (r[2][1] - r[1][2]) / s,
            (r[0][2] - r[2][0]) / s,
            (r[1][0] - r[0][1]) / s,
        ]
    n = math.sqrt(_dot(axis, axis))
    return [a / n for a in axis], math.degrees(angle)


def matrix_rows(flat: list[float]) -> list[list[float]]:
    """Rotation rows from a row-major 4×4 ``Matrix3D.asArray()``."""
    return [list(flat[4 * i : 4 * i + 3]) for i in range(3)]


_TABLE_PATH = os.path.join(os.path.dirname(__file__), "part_classes.json")
_table_cache: dict | None = None


def part_classes() -> dict[str, list[str]]:
    """``{"motor": [prefixes], "servo": [...]}`` from part_classes.json."""
    global _table_cache
    if _table_cache is None:
        with open(_TABLE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _table_cache = {k: v for k, v in data.items() if not k.startswith("_")}
        _table_cache["_names"] = data.get("_names", {})
    return {k: v for k, v in _table_cache.items() if not k.startswith("_")}


def name_rules() -> dict[str, list[str]]:
    """``{"motor": [words], ..., "exclude": [words]}`` from part_classes.json."""
    part_classes()
    return _table_cache["_names"]


def classify_part(
    part_number: str,
    name: str,
    table: dict[str, list[str]] | None = None,
    names: dict[str, list[str]] | None = None,
) -> str | None:
    """Class ("motor", "servo", ...) whose prefix starts the part number or
    the component name, case-insensitively. Fallback: a ``names`` word in the
    component name with no exclude word ("Yellow Jacket", not "Motor Mount").
    None if nothing matches."""
    table = part_classes() if table is None else table
    keys = [s.strip().upper() for s in (part_number or "", name or "") if s]
    for cls, prefixes in table.items():
        for p in prefixes:
            if any(k.startswith(p.upper()) for k in keys):
                return cls
    words = name_rules() if names is None else names
    low = (name or "").lower()
    if not low or any(w in low for w in words.get("exclude", [])):
        return None
    for cls, needles in words.items():
        if cls != "exclude" and any(w in low for w in needles):
            return cls
    return None
