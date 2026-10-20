"""Pure helpers for naming assembly parts.

Deliberately free of ``adsk`` imports so lookup and ref parsing can be
unit-tested without a running Fusion instance.

An occurrence is named by its full path (``Drivetrain:1+Channel:2``), its
own name (``Channel:2``), or its component name (``Channel``) when only one
occurrence uses that component. A face/edge ref is
``<occurrence path>/b<body>/f<face>`` or ``.../e<edge>``; an empty path
(``/b0/f3``) means a body in the root component.
"""

from __future__ import annotations

import re

# How many candidate names an ambiguity error lists before eliding the rest.
_MAX_LISTED = 8


def pick_occurrence(name: str, rows: list[tuple[str, str]]) -> int:
    """Index into *rows* of the occurrence *name* refers to.

    *rows* holds ``(full_path, component_name)`` per occurrence. Raises
    RuntimeError when nothing matches, or when the name matches several
    occurrences, listing them so the caller can pick one.
    """
    for i, (path, _) in enumerate(rows):
        if path == name:
            return i

    by_leaf = [i for i, (path, _) in enumerate(rows) if path.split("+")[-1] == name]
    if len(by_leaf) == 1:
        return by_leaf[0]

    matches = by_leaf or [i for i, (_, comp) in enumerate(rows) if comp == name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(
            f"Occurrence '{name}' not found — use list_components to see "
            "occurrence names"
        )
    names = [rows[i][0] for i in matches]
    listed = ", ".join(names[:_MAX_LISTED])
    if len(names) > _MAX_LISTED:
        listed += ", …"
    raise RuntimeError(
        f"'{name}' matches {len(names)} occurrences: {listed} — pass the "
        "occurrence name"
    )


_REF_RE = re.compile(r"^(?P<occ>.*)/b(?P<body>\d+)/(?P<kind>[fe])(?P<idx>\d+)$")


def parse_ref(ref: str) -> tuple[str, int, str, int]:
    """Split a ref into ``(occurrence_path, body_index, kind, index)``.

    *kind* is ``"face"`` or ``"edge"``; *occurrence_path* is ``""`` for a
    root-component body.
    """
    m = _REF_RE.match(ref.strip())
    if m is None:
        raise RuntimeError(
            f"Bad ref '{ref}' — expected '<occurrence>/b<body>/f<face>' or "
            "'<occurrence>/b<body>/e<edge>', e.g. 'Channel:2/b0/f37'"
        )
    kind = "face" if m["kind"] == "f" else "edge"
    return m["occ"], int(m["body"]), kind, int(m["idx"])


def make_ref(occurrence_path: str, body_index: int, kind: str, index: int) -> str:
    """Inverse of :func:`parse_ref`."""
    return f"{occurrence_path}/b{body_index}/{kind[0]}{index}"


def union_bbox(
    boxes: list[tuple[list[float], list[float]]],
) -> tuple[list[float], list[float]] | None:
    """Axis-aligned union of ``(min, max)`` boxes; None if *boxes* is empty."""
    if not boxes:
        return None
    mn = [min(b[0][i] for b in boxes) for i in range(3)]
    mx = [max(b[1][i] for b in boxes) for i in range(3)]
    return mn, mx


def boxes_overlap(
    a: tuple[list[float], list[float]],
    b: tuple[list[float], list[float]],
    tol: float = 1e-6,
) -> bool:
    """True if ``(min, max)`` boxes *a* and *b* touch or overlap."""
    return all(a[0][i] <= b[1][i] + tol and b[0][i] <= a[1][i] + tol for i in range(3))
