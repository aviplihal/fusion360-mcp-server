"""Robot design files, our own mechanism cards, and session knowledge.

* ``kb/designs/<robot>/design.md`` carries what the subsystems of one robot
  agree on (frame, envelopes, interfaces, actuator budget, status). Format:
  ``kb/designs/_template/design.md``.
* ``kb_save_design`` writes an accepted subsystem as our own mechanism card
  under ``kb/robots/ours-<robot>/`` in the format ``kb.py`` indexes.
* ``kb/design_rules.md``, ``kb/lessons.md`` and the current
  ``constraints.json`` are served as MCP resources and inlined in the
  ``work_on_subsystem`` / ``build_whole_robot`` prompts.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from .kb import current_season, default_kb_dir, parse_frontmatter

STATUSES = ("not started", "concept", "built", "accepted")
SPEC_KEYS = (
    "status",
    "component",
    "envelope",
    "extended",
    "motors",
    "servos",
    "interfaces",
    "based_on",
)
NOTABLE_MAX_WORDS = 80
RECIPE_MAX_WORDS = 100

# Mechanism facets from docs/plans/knowledge-base.md ("Cards"). A list is a
# fixed set of choices; None means free text or a number.
FACETS: dict[str, dict[str, list[str] | None]] = {
    "drivetrain": {
        "drive_type": ["mecanum", "tank", "swerve", "h-drive", "other"],
        "wheel": None,
        "motor_count": None,
        "motor": None,
        "gear_ratio": None,
        "odometry": ["pods", "dead wheels", "none", "other"],
        "frame": ["channel", "plates", "custom"],
        "material": None,
    },
    "intake": {
        "intake_type": [
            "roller",
            "compliant wheels",
            "surgical tubing",
            "claw-style",
            "other",
        ],
        "width_mm": None,
        "motors": None,
        "servos": None,
        "deploy": ["fixed", "pivot", "slide"],
        "passes_to": ["shooter", "storage", "claw", "transfer", "other"],
    },
    "shooter": {
        "shooter_type": [
            "single flywheel",
            "double flywheel",
            "counter roller",
            "catapult",
            "other",
        ],
        "wheel_diameter_mm": None,
        "wheel_material": None,
        "compression_mm": None,
        "motor_count": None,
        "motor_rpm": None,
        "gear_ratio": None,
        "hood": ["fixed", "adjustable", "none"],
        "feeder": None,
        "game_piece": ["POLLEN", "NECTAR", "other"],
    },
    "turret": {
        "drive": ["gear", "belt", "chain", "other"],
        "actuator": ["motor", "servo"],
        "bearing": ["lazy susan", "slewing ring", "custom"],
        "homing": ["encoder", "limit switch", "hard stop", "none"],
        "carries": None,
    },
    "transfer": {
        "from": None,
        "to": None,
        "method": [
            "rollers",
            "belts",
            "gravity ramp",
            "servo kicker",
            "indexer wheel",
            "other",
        ],
        "capacity": None,
        "sensing": ["color", "distance", "none"],
        "actuators": None,
    },
    "claw": {
        "actuation": ["servo", "linear servo", "passive"],
        "grip": ["pads", "fingers", "hooks", "other"],
        "dof": None,
        "material": None,
    },
    "power_transmission": {
        "purpose": None,
        "switching": ["servo dog shift", "ratchet", "differential", "other"],
        "input_motors": None,
        "outputs": None,
        "ratios": None,
        "locking": None,
    },
}
# Types that stay generic (no facets) until there are ~10 examples.
GENERIC_TYPES = ("slide", "arm", "hang", "outtake", "other")

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SECTION_RE = re.compile(r"^## +(.+?)\s*$")
_COMMENT_RE = re.compile(r"\A\s*<!--.*?-->\s*", re.S)


def slug(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    if not s:
        raise ValueError("Give a robot or subsystem name (letters or digits).")
    return s


def _today() -> str:
    return datetime.date.today().isoformat()


def _words(text: str | None) -> int:
    return len((text or "").split())


def _one_line(text) -> str:
    return " ".join(str(text).split())


# ── game limits ──────────────────────────────────────────────────────


def load_constraints(kb_dir: Path) -> dict:
    season = current_season(kb_dir)
    path = kb_dir / "rules" / season / "constraints.json" if season else None
    if path and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def limits(kb_dir: Path) -> dict:
    """Start cube, expansion box, actuator caps and season label (with defaults)."""
    c = load_constraints(kb_dir)
    act = c.get("actuators") or {}
    season = " ".join(str(c[k]) for k in ("season", "game") if c.get(k))
    return {
        "cube": (c.get("starting_size") or {}).get("box") or [45.7, 45.7, 45.7],
        "expansion": (c.get("expansion_size") or {}).get("box") or [45.7, 61.0, 73.65],
        "max_motors": (act.get("max_motors") or {}).get("count", 8),
        "max_servos": (act.get("max_servos") or {}).get("count", 8),
        "season": season or (current_season(kb_dir) or ""),
    }


def constraints_summary(kb_dir: Path) -> str:
    c = load_constraints(kb_dir)
    lim = limits(kb_dir)
    cube = "×".join(f"{v:g}" for v in lim["cube"])
    exp = "×".join(f"{v:g}" for v in lim["expansion"])
    lines = [
        f"{lim['season'] or 'Season ?'}"
        + (f" (manual {c['manual_version']})" if c.get("manual_version") else "")
        + ", units cm.",
        f"Start (R102): fits a {cube} cube. Extended (R105): {exp}, last number "
        "is height above the tiles, held mechanically.",
        f"Actuators (R503): ≤ {lim['max_motors']} motors and ≤ "
        f"{lim['max_servos']} servos in total.",
    ]
    pieces = c.get("scoring_elements") or {}
    if pieces:
        lines.append(
            "Game pieces: "
            + ", ".join(f"{k} Ø{v.get('diameter_cm')} cm" for k, v in pieces.items())
            + "."
        )
    return "\n".join(lines)


# ── robot design file ────────────────────────────────────────────────


def design_path(kb_dir: Path, robot: str) -> Path:
    return kb_dir / "designs" / slug(robot) / "design.md"


def _read_design(kb_dir: Path, robot: str) -> tuple[Path, list[str]]:
    path = design_path(kb_dir, robot)
    if not path.is_file():
        raise FileNotFoundError(
            f"No design file for '{robot}' ({path}). "
            "Create it with robot_design action=create."
        )
    return path, path.read_text(encoding="utf-8").splitlines()


def _sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Heading text → (heading line index, end index exclusive)."""
    heads = [
        (i, m.group(1)) for i, ln in enumerate(lines) if (m := _SECTION_RE.match(ln))
    ]
    out = {}
    for n, (i, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        out[title] = (i, end)
    return out


def parse_design(lines: list[str]) -> dict[str, dict]:
    """Subsystem key → spec dict, in file order."""
    subs = {}
    for title, (start, end) in _sections(lines).items():
        if not title.lower().startswith("subsystem:"):
            continue
        key = slug(title.split(":", 1)[1])
        spec: dict = {}
        for ln in lines[start + 1 : end]:
            if ln.startswith("spec:"):
                try:
                    spec = json.loads(ln[5:])
                except ValueError as exc:
                    raise ValueError(f"Bad spec line in '{key}': {exc}") from exc
                break
        subs[key] = spec
    return subs


def _box_ok(box, name: str) -> list[float]:
    if not isinstance(box, dict) or not all(
        isinstance(box.get(k), list) and len(box[k]) == 3 for k in ("min", "max")
    ):
        raise ValueError(
            f'{name} must be {{"min": [x, y, z], "max": [x, y, z]}} in cm.'
        )
    lo, hi = [float(v) for v in box["min"]], [float(v) for v in box["max"]]
    if any(a >= b for a, b in zip(lo, hi)):
        raise ValueError(f"{name}: every min must be smaller than its max.")
    return lo + hi


def validate(subs: dict[str, dict], lim: dict) -> tuple[list[str], list[str]]:
    """Errors (must fix) and warnings (worth a look) for the whole design."""
    errors, warnings = [], []
    cx, cy, cz = lim["cube"][0] / 2, lim["cube"][1] / 2, lim["cube"][2]
    boxes = {}
    for key, s in subs.items():
        if s.get("status", "not started") not in STATUSES:
            errors.append(f"{key}: status must be one of {', '.join(STATUSES)}.")
        for field in ("motors", "servos"):
            v = s.get(field, 0)
            if not isinstance(v, int) or v < 0:
                errors.append(f"{key}: {field} must be a whole number ≥ 0.")
        env = s.get("envelope")
        if env is not None:
            try:
                x0, y0, z0, x1, y1, z1 = _box_ok(env, f"{key} envelope")
            except ValueError as exc:
                errors.append(str(exc))
            else:
                boxes[key] = (x0, y0, z0, x1, y1, z1)
                if x0 < -cx or x1 > cx or y0 < -cy or y1 > cy or z0 < 0 or z1 > cz:
                    errors.append(
                        f"{key}: envelope leaves the starting cube (x,y ±{cx:g}, "
                        f"z 0..{cz:g}). Give the stowed box here and the "
                        "fully extended box as `extended`."
                    )
        ext = s.get("extended")
        if ext is not None:
            try:
                x0, y0, z0, x1, y1, z1 = _box_ok(ext, f"{key} extended")
            except ValueError as exc:
                errors.append(str(exc))
            else:
                w, d = sorted([x1 - x0, y1 - y0])
                ew, ed = sorted(lim["expansion"][:2])
                if w > ew or d > ed or z0 < 0 or z1 > lim["expansion"][2]:
                    errors.append(
                        f"{key}: extended box exceeds the expansion limit "
                        f"{ew:g}×{ed:g} cm footprint, height {lim['expansion'][2]:g}."
                    )
        if s.get("status") in ("built", "accepted") and env is None:
            warnings.append(f"{key}: {s['status']} but has no envelope.")
    motors, servos = _totals(subs)
    if motors > lim["max_motors"]:
        errors.append(f"Motors total {motors} > {lim['max_motors']} (R503).")
    if servos > lim["max_servos"]:
        errors.append(f"Servos total {servos} > {lim['max_servos']} (R503).")
    keys = list(boxes)
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            A, B = boxes[a], boxes[b]
            if all(A[k] < B[k + 3] and B[k] < A[k + 3] for k in range(3)):
                warnings.append(f"Envelopes of {a} and {b} overlap (fine if intended).")
    return errors, warnings


def _totals(subs: dict[str, dict]) -> tuple[int, int]:
    def total(field):
        return sum(s.get(field) for s in subs.values() if isinstance(s.get(field), int))

    return total("motors"), total("servos")


def budget_line(subs: dict[str, dict], lim: dict) -> str:
    motors, servos = _totals(subs)
    return (
        f"Budget: motors {motors}/{lim['max_motors']}, "
        f"servos {servos}/{lim['max_servos']}"
    )


def create_design(kb_dir: Path, robot: str) -> Path:
    path = design_path(kb_dir, robot)
    if path.exists():
        raise ValueError(f"Design file already exists: {path}")
    template = kb_dir / "designs" / "_template" / "design.md"
    if not template.is_file():
        raise FileNotFoundError(f"Template missing: {template}")
    text = _COMMENT_RE.sub("", template.read_text(encoding="utf-8"), count=1)
    lim = limits(kb_dir)
    text = (
        text.replace("{robot}", robot.strip())
        .replace("{date}", _today())
        .replace("{season}", lim["season"] or "?")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def get_design(kb_dir: Path, robot: str) -> str:
    path, lines = _read_design(kb_dir, robot)
    subs = parse_design(lines)
    lim = limits(kb_dir)
    errors, warnings = validate(subs, lim)
    head = [f"kb/designs/{path.parent.name}/design.md", budget_line(subs, lim)]
    head += [f"ERROR: {e}" for e in errors] + [f"warning: {w}" for w in warnings]
    return "\n".join(head) + "\n\n" + "\n".join(lines)


def _clean_spec(spec: dict) -> dict:
    ordered = {k: spec[k] for k in SPEC_KEYS if k in spec}
    ordered.update({k: v for k, v in spec.items() if k not in ordered})
    return ordered


def _append_log(lines: list[str], entry: str) -> None:
    secs = _sections(lines)
    if "Change log" not in secs:
        lines += ["", "## Change log"]
        secs = _sections(lines)
    _, end = secs["Change log"]
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, f"- {_today()} {entry}")


def update_subsystem(
    kb_dir: Path, robot: str, subsystem: str, changes: dict
) -> tuple[str, list[str]]:
    """Merge ``changes`` into one subsystem's spec; refuse if the design breaks."""
    path, lines = _read_design(kb_dir, robot)
    key = slug(subsystem)
    changes = {k: v for k, v in changes.items() if k in SPEC_KEYS}
    if not changes:
        raise ValueError(f"Nothing to update. Fields: {', '.join(SPEC_KEYS)}.")
    if "interfaces" in changes and not (
        isinstance(changes["interfaces"], list)
        and all(isinstance(i, dict) and i.get("name") for i in changes["interfaces"])
    ):
        raise ValueError(
            'interfaces: a list of {"name", "where", "provided_by"} objects.'
        )
    subs = parse_design(lines)
    old = subs.get(key)
    spec = dict(
        old
        if old is not None
        else {
            "status": "not started",
            "component": key.replace("-", " ").title().replace(" ", ""),
            "envelope": None,
            "extended": None,
            "motors": 0,
            "servos": 0,
            "interfaces": [],
            "based_on": [],
        }
    )
    spec.update(changes)
    subs[key] = spec
    lim = limits(kb_dir)
    errors, warnings = validate(subs, lim)
    if errors:
        raise ValueError("Not saved: " + " ".join(errors))
    spec_line = "spec: " + json.dumps(_clean_spec(spec), ensure_ascii=False)
    secs = _sections(lines)
    if old is not None:
        start, end = next(
            span
            for title, span in secs.items()
            if title.lower().startswith("subsystem:")
            and slug(title.split(":", 1)[1]) == key
        )
        idx = next(
            (i for i in range(start + 1, end) if lines[i].startswith("spec:")), None
        )
        if idx is None:
            lines.insert(start + 1, spec_line)
        else:
            lines[idx] = spec_line
    else:
        # New subsystem goes before the open questions (or at the end).
        at = secs.get("Open questions", (len(lines), 0))[0]
        lines[at:at] = [f"## Subsystem: {key}", spec_line, "Notes:", ""]
    changed = ", ".join(
        f"{k} {old.get(k) if old else None!r}→{changes[k]!r}"
        if k in ("status", "motors", "servos")
        else k
        for k in changes
    )
    _append_log(lines, f"{key}: {changed}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return budget_line(subs, lim), warnings


def add_note(kb_dir: Path, robot: str, text: str, section: str = "questions") -> str:
    path, lines = _read_design(kb_dir, robot)
    text = _one_line(text or "")
    if not text:
        raise ValueError("Give the note text.")
    if section == "log":
        _append_log(lines, text)
    else:
        secs = _sections(lines)
        if "Open questions" not in secs:
            at = secs.get("Change log", (len(lines), 0))[0]
            lines[at:at] = ["## Open questions", ""]
            secs = _sections(lines)
        _, end = secs["Open questions"]
        while end > 0 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, f"- [ ] {text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return text


def resolve_note(kb_dir: Path, robot: str, text: str, answer: str = "") -> str:
    path, lines = _read_design(kb_dir, robot)
    needle = (text or "").strip().lower()
    hits = [
        i
        for i, ln in enumerate(lines)
        if ln.startswith("- [ ]") and needle in ln.lower()
    ]
    if not needle or len(hits) != 1:
        raise ValueError(
            f"{len(hits)} open questions match '{text}'. Quote part of exactly one."
        )
    i = hits[0]
    lines[i] = "- [x]" + lines[i][5:] + (f" → {_one_line(answer)}" if answer else "")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines[i]


# ── our own mechanism cards ──────────────────────────────────────────


def _check_facets(mtype: str, facets: dict | None) -> dict:
    facets = facets or {}
    if mtype in GENERIC_TYPES:
        if facets:
            raise ValueError(f"Type '{mtype}' has no facets yet; put it in notable.")
        return {}
    allowed = FACETS[mtype]
    for k, v in facets.items():
        if k not in allowed:
            raise ValueError(
                f"Unknown {mtype} facet '{k}'. Allowed: {', '.join(allowed)}."
            )
        if allowed[k] is not None and v not in allowed[k]:
            raise ValueError(f"{k} must be one of: {', '.join(allowed[k])}.")
        if isinstance(v, (dict, list)):
            raise ValueError(f"{k}: one value (text or number), not a list.")
    return facets


def _frontmatter(meta: dict) -> str:
    out = ["---"]
    for k, v in meta.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, str):
            out.append(f"{k}: {_one_line(v)}")
        else:
            out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(out + ["---", ""])


def save_design_card(
    kb_dir: Path, robot: str, subsystem: str, args: dict
) -> list[Path]:
    """Write kb/robots/ours-<robot>/<subsystem>.md and update robot.md."""
    rslug, key = slug(robot), slug(subsystem)
    _, lines = _read_design(kb_dir, robot)
    spec = parse_design(lines).get(key)
    if spec is None:
        raise ValueError(
            f"'{key}' is not in the design file. Add it with robot_design."
        )
    if spec.get("status") != "accepted":
        raise ValueError(
            f"'{key}' is '{spec.get('status')}'. Save only accepted subsystems: "
            "set status accepted with robot_design first."
        )
    mtype = args.get("type") or key
    if mtype not in FACETS and mtype not in GENERIC_TYPES:
        raise ValueError(
            f"Give type: one of {', '.join(list(FACETS) + list(GENERIC_TYPES))}."
        )
    facets = _check_facets(mtype, args.get("facets"))
    notable = _one_line(args.get("notable") or "")
    if not notable:
        raise ValueError("notable is required: what's different about this design.")
    if _words(notable) > NOTABLE_MAX_WORDS:
        raise ValueError(
            f"notable has {_words(notable)} words; the cap is {NOTABLE_MAX_WORDS}."
        )
    recipe = []
    for field, heading in (
        ("brief", "Brief"),
        ("decisions", "Decisions and why"),
        ("results", "Results"),
    ):
        text = (args.get(field) or "").strip()
        if _words(text) > RECIPE_MAX_WORDS:
            raise ValueError(
                f"{field} has {_words(text)} words; the cap is {RECIPE_MAX_WORDS}."
            )
        if text:
            recipe += ["", f"## {heading}", text]
    materials = args.get("materials")
    if isinstance(materials, str):
        materials = [materials]
    lim = limits(kb_dir)
    rating = {"basis": "ours", "multiplier": 1.0}
    source = {"site": "ours", "design": f"kb/designs/{rslug}/design.md"}
    card = _frontmatter(
        {
            "type": mtype,
            "name": args.get("name") or f"{robot.strip()} {key}",
            "path": spec.get("component") or key,
            "season": lim["season"],
            "source": source,
            "facets": facets,
            "rating": rating,
            "motors": args.get("motors", spec.get("motors", 0)),
            "servos": args.get("servos", spec.get("servos", 0)),
            "materials": materials,
            "ideas": args.get("ideas"),
            "based_on": args.get("based_on") or spec.get("based_on"),
            "variant_of": args.get("variant_of"),
            "saved": _today(),
        }
    )
    folder = kb_dir / "robots" / f"ours-{rslug}"
    folder.mkdir(parents=True, exist_ok=True)
    mech_path = folder / f"{key}.md"
    mech_path.write_text(
        card + "\n" + notable + "\n" + "\n".join(recipe) + ("\n" if recipe else ""),
        encoding="utf-8",
    )

    robot_path = folder / "robot.md"
    meta, body = (
        parse_frontmatter(robot_path.read_text(encoding="utf-8"))
        if robot_path.is_file()
        else ({}, "")
    )
    mechs = [m for m in (meta.get("mechanisms") or []) if m != key] + [key]
    body = body.strip()
    if args.get("summary"):
        body = _one_line(args["summary"])
    elif not body or body.startswith("Our own design."):
        body = f"Our own design. Accepted subsystems: {', '.join(mechs)}."
    robot_path.write_text(
        _frontmatter(
            {
                "id": f"ours-{rslug}",
                "title": meta.get("title") or f"{robot.strip()} (our robot)",
                "entry": "robot",
                "season": meta.get("season") or lim["season"],
                "source": source,
                "rating": rating,
                "mechanisms": mechs,
            }
        )
        + "\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return [robot_path, mech_path]


# ── resources and prompts ────────────────────────────────────────────

RESOURCES = {
    "kb://design-rules": (
        "Design rules",
        "Tolerances and rules for FDM, laser-cut wood and aluminum, fasteners",
        "design_rules.md",
        "text/markdown",
    ),
    "kb://lessons": (
        "Lessons",
        "Design tricks and Fusion/MCP gotchas from past sessions",
        "lessons.md",
        "text/markdown",
    ),
    "kb://constraints": (
        "Game constraints",
        "Current season's robot limits (size, actuators, game pieces), cm",
        None,
        "application/json",
    ),
}


def read_kb_resource(uri: str, kb_dir: Path | None = None) -> str:
    kb_dir = Path(kb_dir) if kb_dir else default_kb_dir()
    if uri not in RESOURCES:
        raise ValueError(f"Unknown resource: {uri}")
    name = RESOURCES[uri][2]
    if name is None:
        return json.dumps(load_constraints(kb_dir), indent=2)
    path = kb_dir / name
    return (
        path.read_text(encoding="utf-8")
        if path.is_file()
        else f"({path} not written yet)"
    )


PROMPTS = {
    "work_on_subsystem": (
        "One subsystem session: the 8-step loop plus the robot's design file, "
        "design rules, lessons and game constraints",
        ["robot", "subsystem"],
    ),
    "build_whole_robot": (
        "'Do it all': run the subsystem loop for every unfinished subsystem, "
        "then the robot-level checks",
        ["robot"],
    ),
}

_LOOP = """\
Loop (STOP = wait for the user):
1 Load: context is below. Open the robot's Fusion document; work only inside component "{component}" (create it if missing; show the envelope as a transparent box).
2 Brief: ask what it needs, what to watch out for, any old version. STOP.
3 Research: kb_search kind=mechanism type={mtype} (+ kind=idea), kb_get the best 3–5.
4 Concepts: 2–3 with key numbers (size, motors/servos, ratios, materials) and trade-offs, inside the envelope and budget. STOP: user picks. Then robot_design update_subsystem status=concept based_on=[ids].
5 Build: goBILDA via kb_find_part → insert_part → join_on_holes; custom parts to the design rules (say which process: laser wood, laser aluminum, FDM). Mount to the interfaces in the design file; if the part you mount to isn't built yet, use the interface as written.
6 Checks, report each pass/fail: S1 fits envelope (get_bounding_box), S2 no interference with built subsystems (check_interference), S3 actuators within its budget, S4 list_joints healthy + set_joint_value through the range. Then status=built.
7 Verdict: STOP: user accepts or sends back. kb_feedback with only the entries that caused the verdict.
8 Save: save the document; robot_design update_subsystem (status=accepted, actual envelope, interfaces, motors, servos); add_note for anything other subsystems must know; kb_save_design. Add reusable lessons to kb/lessons.md.
Never use execute_code. Units are cm."""  # noqa: E501


def _context(kb_dir: Path, robot: str) -> tuple[str, dict[str, dict]]:
    try:
        path, lines = _read_design(kb_dir, robot)
        subs = parse_design(lines)
        design = f"## Design file ({path.name})\n" + "\n".join(lines)
    except FileNotFoundError:
        subs = {}
        design = (
            f"## Design file\nNone yet for '{robot}'. Create it first: "
            "robot_design action=create, then agree the frame and envelopes "
            "with the user."
        )
    parts = [
        design,
        "## Game constraints\n" + constraints_summary(kb_dir),
        "## Design rules\n" + read_kb_resource("kb://design-rules", kb_dir),
        "## Lessons\n" + read_kb_resource("kb://lessons", kb_dir),
    ]
    return "\n\n".join(parts), subs


def subsystem_prompt(kb_dir: Path | None, robot: str, subsystem: str) -> str:
    kb_dir = Path(kb_dir) if kb_dir else default_kb_dir()
    if not robot or not subsystem:
        raise ValueError("work_on_subsystem needs robot and subsystem.")
    context, subs = _context(kb_dir, robot)
    key = slug(subsystem)
    spec = subs.get(key) or {}
    component = spec.get("component") or key.title()
    mtype = key if key in FACETS or key in GENERIC_TYPES else "<type>"
    head = f"Subsystem session: {key} of robot {robot}."
    if spec:
        head += (
            f" Now: {spec.get('status')}, envelope {json.dumps(spec.get('envelope'))}, "
            f"budget {spec.get('motors', 0)} motors / {spec.get('servos', 0)} servos."
        )
    elif subs:
        head += (
            " Not in the design file yet: add it with robot_design update_subsystem."
        )
    return "\n".join(
        [head, _LOOP.format(component=component, mtype=mtype), "", context]
    )


def whole_robot_prompt(kb_dir: Path | None, robot: str) -> str:
    kb_dir = Path(kb_dir) if kb_dir else default_kb_dir()
    if not robot:
        raise ValueError("build_whole_robot needs robot.")
    context, subs = _context(kb_dir, robot)
    todo = [k for k, s in subs.items() if s.get("status") != "accepted"]
    if "drivetrain" in todo:
        todo.remove("drivetrain")
        todo.insert(0, "drivetrain")
    text = (
        f"Build robot {robot}, every subsystem in one go. Order: "
        f"{', '.join(todo) or 'all subsystems are accepted'} (drivetrain first; "
        "the others mount to it). For each, run the subsystem loop below. Stop "
        "for the brief and the concept pick unless the user said to choose for "
        "them, and report every check result.\n"
        "When all are accepted: robot checks P1 start cube, P2 extended box "
        "(set_joint_value to max), P3 ≤ 8 motors / 8 servos (check_robot_rules), "
        "P4 check_interference stowed, P5 list_joints all healthy.\n\n"
    )
    return (
        text
        + _LOOP.format(component="<Subsystem>", mtype="<subsystem>")
        + "\n\n"
        + context
    )


# ── MCP tool dispatch (schemas live in kb_tools.py) ──────────────────


def call_design_tool(name: str, args: dict, kb_dir: Path) -> tuple[str, bool]:
    """Run robot_design / kb_save_design. Raises ValueError/FileNotFoundError."""
    robot = str(args.get("robot") or "")
    if name == "kb_save_design":
        paths = save_design_card(kb_dir, robot, str(args.get("subsystem") or ""), args)
        rid = paths[0].parent.name
        return (
            f"Saved {rid}/{paths[1].stem} (open with kb_get). "
            f"Robot card {rid} lists: "
            + ", ".join(parse_frontmatter(paths[0].read_text())[0]["mechanisms"]),
            False,
        )
    action = args.get("action")
    if action == "get":
        return get_design(kb_dir, robot), False
    if action == "create":
        path = create_design(kb_dir, robot)
        return f"Created kb/designs/{path.parent.name}/design.md\n\n" + get_design(
            kb_dir, robot
        ), False
    if action == "update_subsystem":
        changes = {k: args[k] for k in SPEC_KEYS if k in args}
        budget, warnings = update_subsystem(
            kb_dir, robot, str(args.get("subsystem") or ""), changes
        )
        return "\n".join(
            [f"Updated {slug(args.get('subsystem') or '')}. {budget}"]
            + [f"warning: {w}" for w in warnings]
        ), False
    if action == "add_note":
        text = add_note(
            kb_dir,
            robot,
            str(args.get("text") or ""),
            args.get("section") or "questions",
        )
        return f"Added: {text}", False
    if action == "resolve_note":
        line = resolve_note(
            kb_dir, robot, str(args.get("text") or ""), str(args.get("answer") or "")
        )
        return f"Resolved: {line}", False
    return (
        f"Unknown action {action!r}: get, create, update_subsystem, add_note, "
        "resolve_note",
        True,
    )
