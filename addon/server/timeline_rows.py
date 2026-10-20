"""Pure helpers that turn Fusion timeline items into compact rows.

Deliberately free of ``adsk`` imports so formatting and paging can be
unit-tested without a running Fusion instance.
"""

from __future__ import annotations

# adsk.fusion.FeatureHealthStates values.
HEALTH = {
    0: "healthy",
    1: "warning",
    2: "error",
    3: "suppressed",
    4: "rolled_back",
    5: "unknown",
}
PROBLEMS = ("warning", "error")
_MESSAGE_CHARS = 200


def health_name(code: int) -> str:
    return HEALTH.get(code, str(code))


def short_type(object_type: str | None) -> str:
    """``adsk::fusion::ExtrudeFeature`` -> ``Extrude``."""
    if not object_type:
        return "?"
    name = object_type.rsplit("::", 1)[-1]
    if name.endswith("Feature") and len(name) > len("Feature"):
        name = name[: -len("Feature")]
    return name


def first_line(message: str | None) -> str:
    return (message or "").strip().split("\n")[0][:_MESSAGE_CHARS]


def row(i, name, object_type, suppressed, health_code, message=None) -> dict:
    out = {
        "i": i,
        # Occurrence items have a leading space (" Part:1").
        "name": (name or "").strip(),
        "type": short_type(object_type),
        "suppressed": bool(suppressed),
        "health": health_name(health_code),
    }
    if out["health"] in PROBLEMS:
        out["message"] = first_line(message)
    return out


def group_row(i, name, suppressed, children: list[dict]) -> dict:
    """One row for a collapsed group. Fusion reports a group's own health as
    unknown, so take the worst child; list only the unhealthy children."""
    issues = [c for c in children if c["health"] in PROBLEMS]
    if any(c["health"] == "error" for c in issues):
        health = "error"
    elif issues:
        health = "warning"
    else:
        health = "healthy"
    out = {
        "i": i,
        "name": (name or "").strip(),
        "type": "Group",
        "suppressed": bool(suppressed),
        "health": health,
        "items": len(children),
    }
    if issues:
        out["issues"] = issues
    return out


def is_problem(r: dict) -> bool:
    return r["health"] in PROBLEMS


def page(rows: list[dict], offset: int = 0, limit: int = 100, errors_only=False):
    """``(selected rows, number matching before paging)``."""
    if errors_only:
        rows = [r for r in rows if is_problem(r)]
    offset = max(int(offset or 0), 0)
    limit = max(int(limit or 0), 1)
    return rows[offset : offset + limit], len(rows)
