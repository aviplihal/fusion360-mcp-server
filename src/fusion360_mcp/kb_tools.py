"""MCP tools for the knowledge base. Handled in this server, never forwarded to Fusion.

Output is plain text, one line per search hit, to keep tokens low.
"""

from __future__ import annotations

import mcp.types as types

from .kb import KINDS, KnowledgeBase

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
for _t in KB_TOOLS:
    _t["annotations"] = dict(_ANNOTATIONS)

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
        else:
            return _result(f"Unknown knowledge base tool: {name}", error=True)
    except (FileNotFoundError, ValueError) as exc:
        return _result(f"{name}: {exc}", error=True)
    return _result(text)


def _result(text: str, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], isError=error
    )
