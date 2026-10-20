"""MCP tools for the knowledge base. Handled in this server, never forwarded to Fusion.

Output is plain text, one line per search hit, to keep tokens low.
"""

from __future__ import annotations

import mcp.types as types

from . import kb_parts
from .kb import KINDS, VERDICTS, KnowledgeBase

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

KB_TOOLS.append(
    {
        "name": "kb_find_part",
        "title": "Find a goBILDA part",
        "description": (
            "Find real goBILDA parts by SKU, name or exact filters, and get a local "
            "STEP file for insert_part. `name` takes free text ('104mm mecanum "
            "wheel') or a part name from another team's CAD ('Sonic Hub - 8mm REX "
            "(GB)', '... 5203-2402-0019'); every number in it (104mm, 20t, 6000rpm) "
            "must match exactly. Lengths match exactly unless you give "
            "length_tol_mm. One line per part: sku · name · type · key dims · "
            "mass · STEP status. download=true fetches the STEP file of the single "
            "matching part (once; cached) and returns its path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "e.g. '1309-0016-4008'"},
                "name": {"type": "string", "description": "Free text or CAD name"},
                "type": {"type": "string", "enum": list(kb_parts.PART_TYPES)},
                "series": {"type": "string", "description": "e.g. '1120', '5203'"},
                "counts_as": {
                    "type": "string",
                    "enum": list(kb_parts.COUNTS_AS),
                    "description": "For the 8 motor / 8 servo rule",
                },
                "length_mm": {"type": "number"},
                "length_tol_mm": {"type": "number", "minimum": 0, "default": 0},
                "download": {
                    "type": "boolean",
                    "description": "Download the STEP file (needs exactly 1 match)",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
            },
        },
        # Only download=true writes, and only to the STEP cache.
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    }
)
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
        elif name == "kb_find_part":
            return _find_part(kb, args)
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


def _find_part(kb: KnowledgeBase, args: dict) -> types.CallToolResult:
    filters = {k: args.get(k) for k in ("sku", "name", "type", "series", "counts_as")}
    if not any(filters.values()) and args.get("length_mm") is None:
        return _result("Give a sku, name or at least one filter.", error=True)
    length = args.get("length_mm")
    parts = kb.find_parts(
        **filters,
        length_mm=float(length) if length is not None else None,
        length_tol_mm=float(args.get("length_tol_mm") or 0),
        limit=int(args.get("limit") or 10),
    )
    if not parts:
        return _result(
            "No parts match. Numbers must match exactly: drop one or add "
            "length_tol_mm."
        )
    if args.get("download"):
        if len(parts) != 1:
            return _result(
                f"download needs exactly 1 match, got {len(parts)}; pass the sku.\n"
                + "\n".join(kb_parts.part_line(p) for p in parts),
                error=True,
            )
        try:
            path = kb_parts.download_step(parts[0]["sku"], parts[0]["step_url"])
        except (OSError, ValueError) as exc:
            return _result(f"kb_find_part: STEP download failed: {exc}", error=True)
        return _result(f"{kb_parts.part_line(parts[0])}\nSTEP file: {path}")
    return _result("\n".join(kb_parts.part_line(p) for p in parts))


def _result(text: str, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], isError=error
    )
