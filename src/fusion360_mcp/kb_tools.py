"""MCP tools for the knowledge base. Handled in this server, never forwarded to Fusion.

Output is plain text, one line per search hit, to keep tokens low.
"""

from __future__ import annotations

import mcp.types as types

from .kb import KINDS, VERDICTS, KnowledgeBase
from .kb_design import FACETS, GENERIC_TYPES, STATUSES, call_design_tool

MECHANISM_TYPES = [
    "drivetrain",
    "intake",
    "shooter",
    "turret",
    "transfer",
    "claw",
    "power_transmission",
    "slide",
    "arm",
    "hang",
    "outtake",
    "other",
]

_ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

KB_TOOLS: list[dict] = [
    {
        "name": "kb_search",
        "title": "Search the knowledge base",
        "description": (
            "Search past FTC robots, mechanisms, reusable design ideas, the current "
            "game manual's rules, and reference books. Use it before designing a "
            "mechanism (find how other teams built it) and to check rules. Returns "
            "one line per hit, best first; robots from stronger teams rank higher. "
            "Open a hit with kb_get. Filters can be used without a query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free text, e.g. 'counter roller hood'",
                },
                "kind": {
                    "type": "string",
                    "enum": list(KINDS),
                    "description": "robot, mechanism, idea, rule or book",
                },
                "type": {
                    "type": "string",
                    "enum": MECHANISM_TYPES,
                    "description": "Mechanism type (for mechanisms and ideas)",
                },
                "season": {
                    "type": "string",
                    "description": "e.g. 'BIOBUZZ' or '2025-26'",
                },
                "facets": {
                    "type": "object",
                    "description": (
                        'Exact facet matches, e.g. {"shooter_type": "counter roller"}'
                    ),
                    "additionalProperties": {"type": ["string", "number"]},
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8},
            },
        },
    },
    {
        "name": "kb_get",
        "title": "Open a knowledge base entry",
        "description": (
            "Open one entry by id from kb_search: a robot (with its mechanisms), a "
            "mechanism card, an idea, a rule (e.g. 'R105') or a book section."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entry id, e.g. 'R105'"}
            },
            "required": ["id"],
        },
    },
]
KB_TOOLS.append(
    {
        "name": "kb_feedback",
        "title": "Record the user's verdict on a design built from the knowledge base",
        "description": (
            "Call this when the user accepts or rejects a part or mechanism you "
            "designed using knowledge base entries. Pass only the entries that "
            "caused the verdict: if a shooter is rejected because of a hood idea "
            "you took from one robot, pass that robot's mechanism (and the idea), "
            "not everything you opened. Liked entries rank higher in later "
            "searches, disliked ones lower."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Entry ids from kb_search/kb_get",
                },
                "verdict": {"type": "string", "enum": list(VERDICTS)},
                "design": {
                    "type": "string",
                    "description": "What you built, e.g. 'BIOBUZZ shooter v1'",
                },
                "reason": {
                    "type": "string",
                    "description": "Why the user liked or rejected it, in their words",
                },
            },
            "required": ["entries", "verdict", "design", "reason"],
        },
    }
)
for _t in KB_TOOLS:
    _t["annotations"] = dict(_ANNOTATIONS)
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
KB_TOOLS[-1]["annotations"] = _WRITE

_BOX = {
    "type": ["object", "null"],
    "description": 'Box in robot coordinates, cm: {"min": [x,y,z], "max": [x,y,z]}',
    "properties": {
        "min": {"type": "array", "items": {"type": "number"}},
        "max": {"type": "array", "items": {"type": "number"}},
    },
}
KB_TOOLS += [
    {
        "name": "robot_design",
        "title": "Read or update a robot's design file",
        "description": (
            "The robot design file (kb/designs/<robot>/design.md) holds what the "
            "subsystems agree on: frame (origin at the footprint centre on the "
            "tiles, +x right, +y front, +z up, cm), and per subsystem its envelope, "
            "interfaces, motor/servo budget, status and the KB entries it was based "
            "on. get: the file plus budget totals and problems. create: new file "
            "from the template. update_subsystem: change only the fields you pass "
            "(refused if motors or servos total > 8 or the stowed envelope leaves "
            "the 45.7 cm start cube; give moving parts an `extended` box). "
            "add_note: an open question for other subsystems (section=log for a "
            "change-log line). resolve_note: mark the question containing `text` "
            "answered."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get",
                        "create",
                        "update_subsystem",
                        "add_note",
                        "resolve_note",
                    ],
                },
                "robot": {"type": "string", "description": "Robot name, e.g. 'bb1'"},
                "subsystem": {
                    "type": "string",
                    "description": "e.g. drivetrain, intake, transfer, shooter, turret",
                },
                "status": {"type": "string", "enum": list(STATUSES)},
                "component": {
                    "type": "string",
                    "description": "Top-level Fusion component name",
                },
                "envelope": {
                    **_BOX,
                    "description": "Stowed box. " + _BOX["description"],
                },
                "extended": {
                    **_BOX,
                    "description": "Fully extended box, if it moves out",
                },
                "motors": {"type": "integer", "minimum": 0},
                "servos": {"type": "integer", "minimum": 0},
                "interfaces": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "where": {"type": "string"},
                            "provided_by": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                    "description": "Mount holes, shafts, plates; replaces the list",
                },
                "based_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "KB entry ids",
                },
                "text": {"type": "string", "description": "Note, or text to resolve"},
                "answer": {"type": "string", "description": "resolve_note: the answer"},
                "section": {"type": "string", "enum": ["questions", "log"]},
            },
            "required": ["action", "robot"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "kb_save_design",
        "title": "Save an accepted subsystem as our own mechanism card",
        "description": (
            "Step 8 of a subsystem session, after the user accepted it and "
            "robot_design marks it accepted. Writes kb/robots/ours-<robot>/"
            "<subsystem>.md (and robot.md) so later searches find our design, "
            "ranked above other teams'. Facets must come from the type's list "
            "(kb_get any card of that type to see them); notable ≤ 80 words, "
            "only what differs from normal; brief/decisions/results ≤ 100 words each. "
            "motors, servos, component and based_on default to the design file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string"},
                "subsystem": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": list(FACETS) + list(GENERIC_TYPES),
                    "description": "Mechanism type (default: the subsystem name)",
                },
                "name": {"type": "string", "description": "Short card title"},
                "facets": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number"]},
                },
                "notable": {"type": "string", "description": "≤ 80 words"},
                "materials": {"type": "array", "items": {"type": "string"}},
                "ideas": {"type": "array", "items": {"type": "string"}},
                "based_on": {"type": "array", "items": {"type": "string"}},
                "motors": {"type": "integer", "minimum": 0},
                "servos": {"type": "integer", "minimum": 0},
                "brief": {"type": "string", "description": "What the user asked for"},
                "decisions": {"type": "string", "description": "Choices and why"},
                "results": {"type": "string", "description": "Check results, issues"},
                "variant_of": {"type": "string", "description": "Earlier card id"},
                "summary": {"type": "string", "description": "Robot card summary"},
            },
            "required": ["robot", "subsystem", "notable"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
]
_DESIGN_TOOLS = {"robot_design", "kb_save_design"}

_KB_NAMES = {t["name"] for t in KB_TOOLS}
_kb: KnowledgeBase | None = None


def is_kb_tool(name: str) -> bool:
    return name in _KB_NAMES


def get_kb_tool_list() -> list[types.Tool]:
    return [
        types.Tool(
            name=t["name"],
            title=t["title"],
            description=t["description"],
            inputSchema=t["inputSchema"],
            annotations=types.ToolAnnotations(**t["annotations"]),
        )
        for t in KB_TOOLS
    ]


def _knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


# ── formatting ───────────────────────────────────────────────────────

_SKIP_META = {
    "id",
    "title",
    "name",
    "kind",
    "facets",
    "rating",
    "mechanisms",
    "ideas",
    "render",
    "reviewed",
    "team",
    "source",
}

# The facets that best describe each mechanism type, shown first in hit lines.
KEY_FACETS = {
    "drivetrain": ["drive_type", "wheel", "gear_ratio"],
    "intake": ["intake_type", "deploy", "passes_to"],
    "shooter": ["shooter_type", "wheel_diameter_mm", "hood"],
    "turret": ["drive", "actuator", "bearing"],
    "transfer": ["method", "capacity", "sensing"],
    "claw": ["actuation", "grip", "dof"],
    "power_transmission": ["switching", "purpose", "outputs"],
}


def _facet_summary(meta: dict, mtype: str | None, n: int = 3) -> str:
    facets = meta.get("facets") if isinstance(meta.get("facets"), dict) else {}
    facets = {k: v for k, v in facets.items() if v not in (None, "", "other")}
    order = [k for k in KEY_FACETS.get(mtype or "", []) if k in facets]
    order += [k for k in facets if k not in order]
    # Numbers mean nothing without their name ("72"), so label them.
    return ", ".join(
        f"{k}={facets[k]}" if isinstance(facets[k], (int, float)) else str(facets[k])
        for k in order[:n]
    )


def hit_line(d: dict) -> str:
    kind, meta = d["kind"], d["meta"]
    parts = [d["id"]]
    if kind == "mechanism":
        parts += [d["type"] or "mechanism", d["title"], _facet_summary(meta, d["type"])]
    elif kind == "robot":
        parts += ["robot", d["title"], d["season"] or "season ?", d["team"] or "team ?"]
    elif kind == "idea":
        parts += [
            f"idea/{d['type'] or 'any'}",
            d["title"],
            f"seen in {len(meta.get('seen_in') or [])}",
        ]
    else:
        page = meta.get("page")
        parts += [kind, d["title"]] + ([f"p.{page}"] if page else [])
    if kind in ("robot", "mechanism") and d["multiplier"] != 1.0:
        parts.append(f"{d['multiplier']:.2f}×")
    if d.get("likes") or d.get("dislikes"):
        parts.append(
            f"used in {d['likes'] + d['dislikes']} designs: "
            f"{d['likes']} liked, {d['dislikes']} disliked"
        )
    line = " · ".join(p for p in parts if p)
    if d.get("snip") and kind in ("rule", "book"):
        line += "\n    " + " ".join(d["snip"].split())
    return line


def _meta_lines(d: dict) -> list[str]:
    meta = d["meta"]
    lines = []
    if d.get("team"):
        lines.append(f"team: {d['team']}")
    source = meta.get("source")
    if isinstance(source, dict):
        lines.append(
            "source: "
            + " ".join(str(source[k]) for k in ("site", "url") if source.get(k))
        )
    elif source:
        lines.append(f"source: {source}")
    for key, value in meta.items():
        if key in _SKIP_META or value in (None, "", [], {}):
            continue
        lines.append(f"{key}: {value}")
    facets = meta.get("facets")
    if isinstance(facets, dict) and facets:
        lines.append(
            "facets: "
            + "; ".join(f"{k}={v}" for k, v in facets.items() if v not in (None, ""))
        )
    rating = meta.get("rating")
    if isinstance(rating, dict):
        detail = rating.get("detail") or rating.get("basis") or ""
        lines.append(f"rating: {d['multiplier']:.2f}× {detail}".rstrip())
    if d.get("likes") or d.get("dislikes"):
        lines.append(
            f"feedback: {d['feedback']:.2f}× ({d['likes']} liked, "
            f"{d['dislikes']} disliked)"
        )
    return lines


def format_doc(d: dict) -> str:
    out = [
        f"{d['id']} · {d['kind']}" + (f"/{d['type']}" if d["type"] else ""),
        d["title"],
    ]
    out += _meta_lines(d)
    if d["body"] and d["body"] != d["title"]:
        out += ["", d["body"]]
    children = d.get("children")
    if children:
        out += ["", "Mechanisms (open with kb_get):"]
        out += [f"  {hit_line(c)}" for c in children]
    return "\n".join(out)


# ── dispatch ─────────────────────────────────────────────────────────


def call_kb_tool(
    name: str, arguments: dict | None, kb: KnowledgeBase | None = None
) -> types.CallToolResult:
    args = arguments or {}
    kb = kb or _knowledge_base()
    try:
        if name == "kb_search":
            hits = kb.search(
                args.get("query") or "",
                kind=args.get("kind"),
                type=args.get("type"),
                season=args.get("season"),
                facets=args.get("facets"),
                limit=int(args.get("limit") or 8),
            )
            if not hits:
                text = "No matches. Try fewer words or fewer filters."
            else:
                text = "\n".join(hit_line(h) for h in hits)
        elif name == "kb_get":
            doc = kb.get(str(args.get("id", "")))
            if doc:
                text = format_doc(doc)
            else:
                close = kb.similar_ids(str(args.get("id", "")))
                text = f"No entry '{args.get('id')}'." + (
                    f" Did you mean: {', '.join(close)}?" if close else ""
                )
                return _result(text, error=True)
        elif name in _DESIGN_TOOLS:
            text, error = call_design_tool(name, args, kb.kb_dir)
            return _result(text, error=error)
        elif name == "kb_feedback":
            ids = kb.add_feedback(
                list(args.get("entries") or []),
                str(args.get("verdict", "")),
                str(args.get("design", "")),
                str(args.get("reason", "")),
            )
            text = f"Recorded '{args.get('verdict')}' for: {', '.join(ids)}"
        else:
            return _result(f"Unknown knowledge base tool: {name}", error=True)
    except (FileNotFoundError, ValueError) as exc:
        return _result(f"{name}: {exc}", error=True)
    return _result(text)


def _result(text: str, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], isError=error
    )
