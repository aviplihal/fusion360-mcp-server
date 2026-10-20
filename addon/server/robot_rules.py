"""Pure helpers for check_robot_rules (no adsk import, unit-testable).

Rule values come from the knowledge base (kb/rules/<season>/constraints.json)
so they change with the season, not with the code.
"""

import glob
import json
import os

_AXES = {"x": 0, "y": 1, "z": 2}
_TOL = 1e-3  # cm


def kb_rules_dir() -> str:
    """kb/rules/ of the repo this add-in runs from (the add-in is symlinked)."""
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "kb", "rules")


def load_constraints(rules_dir: str | None = None) -> dict:
    """The latest season's constraints.json (season folders sort by name)."""
    paths = sorted(
        glob.glob(os.path.join(rules_dir or kb_rules_dir(), "*", "constraints.json"))
    )
    if not paths:
        raise RuntimeError(
            "No kb/rules/<season>/constraints.json found — pass 'rules' "
            "(constraints.json keys: starting_size, expansion_size, actuators)"
        )
    with open(paths[-1], encoding="utf-8") as f:
        return json.load(f)


def limits_from(constraints: dict) -> dict:
    """Flatten constraints.json into the shape the checks use."""
    act = constraints.get("actuators", {})
    exp = constraints.get("expansion_size", {})
    return {
        "season": constraints.get("season"),
        "starting_box": constraints.get("starting_size", {}).get("box"),
        "starting_rule": constraints.get("starting_size", {}).get("rule", "R102"),
        "expansion_box": exp.get("box"),
        "expansion_vertical": exp.get("vertical_axis_is"),
        "expansion_rule": exp.get("rule", "R105"),
        "max_motors": act.get("max_motors", {}).get("count"),
        "max_servos": act.get("max_servos", {}).get("count"),
        "actuator_rule": act.get("max_motors", {}).get("rule", "R503"),
    }


def _r(v: float) -> float:
    return round(v, 2)


def fits_box(
    size: list[float], box: list[float], up: str, vertical: float | None
) -> dict:
    """Does an axis-aligned size fit in box (any yaw)?

    With *vertical* given, that box side must hold the up axis and the other
    two sides hold the horizontal sizes in either order. Without it, any
    orientation counts (a cube).
    """
    if vertical is None:
        need, have = sorted(size), sorted(box)
    else:
        up_i = _AXES[up]
        horiz = sorted(s for i, s in enumerate(size) if i != up_i)
        rest = list(box)
        rest.remove(vertical)
        need, have = [*horiz, size[up_i]], [*sorted(rest), vertical]
    over = [_r(n - h) for n, h in zip(need, have) if n > h + _TOL]
    return {"ok": not over, "over_cm": max(over) if over else 0}


def envelope_check(box: tuple, envelope: dict) -> dict:
    """box = (min, max) in cm; envelope = {"min": [...], "max": [...]}."""
    lo, hi = envelope["min"], envelope["max"]
    over = {}
    for i, axis in enumerate("xyz"):
        out = max(lo[i] - box[0][i], box[1][i] - hi[i], 0)
        if out > _TOL:
            over[axis] = _r(out)
    return {"ok": not over, "over_cm": over}


def count_check(counts: dict, budget: dict) -> list[dict]:
    """One row per budgeted class: {"motors": 2} compares with counts["motor"]."""
    rows = []
    for key, limit in budget.items():
        cls = key[:-1] if key.endswith("s") else key
        n = counts.get(cls, 0)
        rows.append({"check": f"{key} ≤ {limit}", "ok": n <= limit, "value": n})
    return rows


def boxes_overlap(a: tuple, b: tuple, tol: float = _TOL) -> bool:
    return all(a[0][i] <= b[1][i] + tol and b[0][i] <= a[1][i] + tol for i in range(3))
