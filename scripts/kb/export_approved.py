"""Export approved robots from the review page into kb/robots/ and kb/ideas.csv.

Step 1 (Claude, with the ArtifactData tool): list the review page's `robots`
collection with out_dir=kb/ingest/drafts/_review  → one JSON file per robot.
Step 2: python3 -I scripts/kb/export_approved.py [kb_dir]

Idempotent: approved robots are rewritten from scratch each run; a robot whose
status is no longer "approved" has its kb/robots/<id>/ folder removed. Ideas
from robots are rebuilt and deduplicated by text; ideas from other sources
(gm0, ours) are kept as they are.

Card format: see docs/plans/knowledge-base.md ("Cards").
"""

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BIAS = {"lower": 0.85, "normal": 1.0, "higher": 1.15}
IDEA_FIELDS = ["id", "mechanism", "text", "tags", "seen_in", "source"]


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].rstrip("-") or "mechanism"


def bias_value(mech: dict) -> float:
    b = mech.get("bias", 1.0)
    if isinstance(b, str):
        b = BIAS.get(b, 1.0)
    return float(b or 1.0)


def fm_line(key: str, value) -> str:
    if isinstance(value, (dict, list, bool)) or value is None:
        value = json.dumps(value, ensure_ascii=False)
    return f"{key}: {value}"


def write_card(path: Path, meta: dict, body: str) -> None:
    lines = ["---"]
    lines += [fm_line(k, v) for k, v in meta.items() if v not in (None, "", [], {})]
    lines += ["---", "", (body or "").strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def save_image(src: Path, dest: Path) -> bool:
    """Copy a render as an ~800 px JPEG (macOS sips); fall back to a plain copy."""
    if not src.is_file():
        return False
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80",
             "-Z", "800", str(src), "--out", str(dest)],
            check=True, capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        shutil.copyfile(src, dest.with_suffix(src.suffix))
    return True


def local_renders(drafts: Path, robot_id: str) -> tuple[Path | None, dict]:
    """Robot render path and {(type, name): render path} from the ingest folder."""
    folder = drafts / robot_id
    draft = folder / "draft.json"
    if not draft.is_file():
        return None, {}
    data = json.loads(draft.read_text())
    robot = folder / data["render_file"] if data.get("render_file") else None
    mechs = {
        (m.get("type"), m.get("name")): folder / m["render_file"]
        for m in data.get("mechanisms", [])
        if m.get("render_file")
    }
    return robot, mechs


def match_render(mech: dict, renders: dict) -> Path | None:
    """Exact (type, name), else a unique name, else a unique type.

    Names and types can change between drafting and review (edits, fixes)."""
    exact = renders.get((mech.get("type"), mech.get("name")))
    if exact:
        return exact
    for i in (1, 0):
        hits = [p for k, p in renders.items() if k[i] == (mech.get("type"), mech.get("name"))[i]]
        if len(hits) == 1:
            return hits[0]
    return None


def idea_id(text: str) -> str:
    norm = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    return "i-" + hashlib.sha1(norm.encode()).hexdigest()[:8]


def export(kb_dir: Path) -> dict:
    drafts = kb_dir / "ingest" / "drafts"
    review = drafts / "_review" / "robots"
    robots_dir = kb_dir / "robots"
    robots_dir.mkdir(exist_ok=True)
    counts = {"exported": 0, "removed": 0, "mechanisms": 0, "ideas": 0, "no_render": 0}
    ideas: dict[str, dict] = {}

    for f in sorted(review.glob("*.json")):
        raw = json.loads(f.read_text())
        doc = raw.get("data", raw)
        robot_id = raw.get("id") or f.stem
        out = robots_dir / robot_id
        if doc.get("status") != "approved":
            if out.exists():
                shutil.rmtree(out)
                counts["removed"] += 1
            continue
        if out.exists():
            shutil.rmtree(out)
        out.mkdir()

        robot_png, mech_pngs = local_renders(drafts, robot_id)
        rating = dict(doc.get("rating") or {"basis": "unknown", "multiplier": 1.0})
        base = float(rating.get("multiplier") or 1.0)

        keys: list[str] = []
        idea_ids_by_type: dict[str, list[str]] = {}
        for idea in doc.get("ideas") or []:
            if idea.get("keep") is False or not idea.get("text"):
                continue
            iid = idea_id(idea["text"])
            row = ideas.setdefault(iid, {
                "id": iid, "mechanism": idea.get("mechanism") or "",
                "text": idea["text"].strip(), "tags": "", "seen_in": [],
                "source": "robots",
            })
            if robot_id not in row["seen_in"]:
                row["seen_in"].append(robot_id)
            idea_ids_by_type.setdefault(idea.get("mechanism") or "", []).append(iid)

        for mech in doc.get("mechanisms") or []:
            if mech.get("dropped"):
                continue
            key = slug(mech.get("name") or mech.get("type") or "mechanism")
            while key in keys or key == "robot":
                key += "-2"
            keys.append(key)
            bias = bias_value(mech)
            mech_rating = {**rating, "multiplier": round(base * bias, 3)}
            if bias != 1.0:
                mech_rating["bias"] = bias
            render = None
            src = match_render(mech, mech_pngs)
            if src and save_image(src, out / f"{key}.jpg"):
                render = f"{key}.jpg"
            elif mech.get("render_url"):
                counts["no_render"] += 1
            write_card(out / f"{key}.md", {
                "type": mech.get("type"),
                "name": mech.get("name"),
                "path": mech.get("path"),
                "season": doc.get("season"),
                "team": doc.get("team"),
                "facets": {k: v for k, v in (mech.get("facets") or {}).items()
                           if v not in (None, "")},
                "rating": mech_rating,
                "ideas": idea_ids_by_type.get(mech.get("type"), []),
                "render": render,
            }, mech.get("notable") or "")
            counts["mechanisms"] += 1

        render = "robot.jpg" if robot_png and save_image(robot_png, out / "robot.jpg") else None
        write_card(out / "robot.md", {
            "id": robot_id,
            "title": doc.get("title"),
            "entry": doc.get("kind") or "robot",  # robot | mechanism (source entry)
            "team": doc.get("team"),
            "season": doc.get("season"),
            "source": doc.get("source"),
            "rating": rating,
            "mechanisms": keys,
            "render": render,
            "reviewed": (doc.get("review") or {}).get("at"),
        }, doc.get("summary") or "")
        counts["exported"] += 1

    # ideas.csv: rebuild robot ideas, keep ideas from other sources.
    path = kb_dir / "ideas.csv"
    kept = []
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as fh:
            kept = [r for r in csv.DictReader(fh) if r.get("source") != "robots"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=IDEA_FIELDS)
        w.writeheader()
        w.writerows(kept)
        for row in sorted(ideas.values(), key=lambda r: (r["mechanism"], r["id"])):
            w.writerow({**row, "seen_in": ";".join(row["seen_in"])})
    counts["ideas"] = len(ideas)
    return counts


if __name__ == "__main__":
    kb = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "kb"
    print(export(kb))
