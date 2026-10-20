"""Pure helpers for driving joint values (set_joint_value).

Deliberately free of ``adsk`` imports so validation and unit conversion
can be unit-tested without a running Fusion instance.

A joint's motion has one or two settable degrees of freedom. Each is a
``(prefix, unit)`` pair: the prefix names the Fusion properties
(``rotationValue`` / ``rotationLimits``, ``slideValue`` / ``slideLimits``)
and the unit is what the tool speaks (degrees or cm; Fusion uses radians
and cm).
"""

from __future__ import annotations

import math

# Index = adsk.fusion.JointTypes value.
JOINT_TYPE_NAMES = (
    "rigid",
    "revolute",
    "slider",
    "cylindrical",
    "pin_slot",
    "planar",
    "ball",
)

# Settable degrees of freedom: value first, value2 second.
DOFS = {
    "revolute": (("rotation", "deg"),),
    "slider": (("slide", "cm"),),
    "cylindrical": (("rotation", "deg"), ("slide", "cm")),
    "pin_slot": (("rotation", "deg"), ("slide", "cm")),
}

_LIMIT_KEYS = ("min", "max", "rest")


def joint_type_name(code: int) -> str:
    if 0 <= code < len(JOINT_TYPE_NAMES):
        return JOINT_TYPE_NAMES[code]
    return str(code)


def to_api(value: float, unit: str) -> float:
    return math.radians(value) if unit == "deg" else float(value)


def from_api(value: float, unit: str) -> float:
    return round(math.degrees(value) if unit == "deg" else value, 4)


def _check_limits(limits, label: str) -> None:
    if limits is None:
        return
    if not isinstance(limits, dict):
        raise RuntimeError(f"{label} must be an object {{min, max, rest}}")
    bad = set(limits) - set(_LIMIT_KEYS)
    if bad:
        raise RuntimeError(
            f"Unknown {label} keys {sorted(bad)} — use min, max, rest "
            "(a number sets and enables it, null disables it)"
        )
    lo, hi = limits.get("min"), limits.get("max")
    if lo is not None and hi is not None and lo > hi:
        raise RuntimeError(f"{label}: min ({lo}) is greater than max ({hi})")


def plan(
    type_name: str,
    value=None,
    value2=None,
    limits=None,
    limits2=None,
) -> list[tuple[str, str, float | None, dict | None]]:
    """Validate a request; return ``[(prefix, unit, value, limits), ...]``
    for each degree of freedom it touches."""
    dofs = DOFS.get(type_name)
    if dofs is None:
        raise RuntimeError(
            f"Joint type '{type_name}' has no settable value — "
            f"set_joint_value handles {', '.join(DOFS)}"
        )
    if value is None and value2 is None and limits is None and limits2 is None:
        raise RuntimeError("Pass value, value2, limits or limits2")
    if len(dofs) == 1 and (value2 is not None or limits2 is not None):
        raise RuntimeError(
            f"A {type_name} joint has one value; value2/limits2 are for "
            "cylindrical and pin_slot joints"
        )
    _check_limits(limits, "limits")
    _check_limits(limits2, "limits2")
    steps = []
    for (prefix, unit), v, lim in zip(dofs, (value, value2), (limits, limits2)):
        if v is not None or lim is not None:
            steps.append((prefix, unit, v, lim))
    return steps


def limit_updates(limits: dict, unit: str) -> list[tuple[str, bool, float | None]]:
    """``[(key, enabled, api_value), ...]`` for each key in *limits*.

    *key* is ``Minimum`` / ``Maximum`` / ``Rest`` (the Fusion property
    stem: ``isMinimumValueEnabled``, ``minimumValue``). A null value
    disables that limit.
    """
    out = []
    for key in _LIMIT_KEYS:
        if key not in limits:
            continue
        stem = {"min": "Minimum", "max": "Maximum", "rest": "Rest"}[key]
        v = limits[key]
        out.append((stem, v is not None, None if v is None else to_api(v, unit)))
    return out


def limits_dict(enabled: dict, values: dict, unit: str) -> dict | None:
    """Report form of a JointLimits: only the enabled ones, in tool units.

    *enabled* and *values* map ``min``/``max``/``rest`` to the Fusion
    flags and values.
    """
    out = {k: from_api(values[k], unit) for k in _LIMIT_KEYS if enabled.get(k, False)}
    return out or None
