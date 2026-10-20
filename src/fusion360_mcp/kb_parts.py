"""goBILDA parts: kb/parts/parts.csv → ``parts`` table, name matching, STEP cache.

parts.csv is written by scripts/kb/scrape_gobilda.py. Filters are exact SQL;
numbers match exactly or within an explicit tolerance, never by similarity.

Name matching (for free text and for part names in other teams' CAD):
  1. A goBILDA SKU (``1309-0016-4008``) anywhere in the name wins outright.
  2. Otherwise the name is normalized into *number tokens* (``104mm``,
     ``6000rpm``, ``20t``, ``30a``, ``m4``, ``2-1``) and *words*. A part
     matches only if it has every number token; matches rank by how many of
     the words they share, then by the shortest name (fewest extra words).
  Onshape FTC-library names like ``Sonic Hub - 8mm REX (GB)`` resolve this way.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import urllib.request
import zipfile
from pathlib import Path

PART_TYPES = (
    "channel",
    "motor",
    "servo",
    "bracket",
    "gear",
    "pulley",
    "sprocket",
    "wheel",
    "bearing",
    "shaft",
    "hub",
    "spacer",
    "hardware",
    "electronics",
    "other",
)
COUNTS_AS = ("motor", "servo", "none")

PARTS_SCHEMA = """
CREATE TABLE parts (
    sku TEXT PRIMARY KEY COLLATE NOCASE,
    name TEXT NOT NULL,
    type TEXT,
    series TEXT,
    length_mm REAL,
    dims TEXT,
    hole_pattern TEXT,
    mass_g REAL,
    price REAL,
    counts_as TEXT,
    product_url TEXT,
    step_url TEXT,
    norm TEXT NOT NULL
);
"""

SKU_RE = re.compile(r"(?<!\d)(\d{4}-\d{4}-\d{4})(?!\d)")
USER_AGENT = "fusion360-mcp-kb/0.1 (FTC robot CAD; STEP download on first use)"

# ── normalization ────────────────────────────────────────────────────

_IGNORED = {
    "gb", "series", "the", "and", "with", "for", "of", "x", "bore", "length",
    "pack", "set", "ratio", "goBILDA".lower(), "mm", "size", "style",
}
_WORD_ALIASES = {
    "aluminium": "aluminum",
    "stainless": "steel",
    "locknut": "nut",
    "nylock": "nylon",
    "gusseted": "gusset",
    "nuts": "nut",
    "teeth": "tooth",
    "bearings": "bearing",
    "wheels": "wheel",
    "gears": "gear",
    "pulleys": "pulley",
    "hubs": "hub",
    "screws": "screw",
    "spacers": "spacer",
    "shafting": "shaft",
}
_UNIT_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mm|rpm|t|tooth|a|hole|v|:1|ah|oz|in)(?![a-z])"
)


def normalize(name: str) -> tuple[set[str], set[str]]:
    """Name → (number tokens, word tokens)."""
    s = (name or "").lower().replace("®", " ").replace("™", " ")
    s = SKU_RE.sub(" ", s)
    s = re.sub(r"[ø⌀]", " ", s)
    # "U-Channel" → "uchannel channel": U beats L, plain "channel" still hits.
    s = re.sub(r"\b([a-z])-([a-z]+)", r"\1\2 \2", s)
    s = re.sub(r"\s+-\s+", " ", s)
    # 8x14x5mm → 8mm 14mm 5mm ; htd5 → 5mm htd ; 4mm id/13mm od → split
    s = re.sub(
        r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm", r"\1mm \2mm \3mm", s
    )
    s = re.sub(r"\bhtd\s?(\d)\b", r"htd \1mm", s)
    s = re.sub(r"\bmod\s*(\d+(?:\.\d+)?)", r"mod\1", s)
    s = s.replace("/", " ")
    numbers: set[str] = set()

    def unit(m: re.Match) -> str:
        num, u = m.group(1), m.group(2)
        u = {"tooth": "t"}.get(u, u)
        numbers.add(num + u)
        return " "

    s = _UNIT_RE.sub(unit, s)
    # Pattern codes "(2-1)", "(43-5)"; M-threads "m4"; module "mod1".
    for tok in re.findall(r"\b\d+-\d+\b|\bm\d+\b|\bmod\d+(?:\.\d+)?\b", s):
        numbers.add(tok)
    s = re.sub(r"\b\d+-\d+\b|\bm\d+\b|\bmod\d+(?:\.\d+)?\b", " ", s)
    words = set()
    for w in re.findall(r"[a-z]+", s):
        w = _WORD_ALIASES.get(w, w)
        if w not in _IGNORED and len(w) > 1:
            words.add(w)
    return numbers, words


def norm_text(name: str) -> str:
    numbers, words = normalize(name)
    return " ".join(sorted(numbers)) + " | " + " ".join(sorted(words))


def head_noun(name: str) -> str:
    """What a part *is*: last word before "(", " - ", " with ", " for "."""
    head = re.split(r"\(| with | for | - ", (name or "").lower(), maxsplit=1)[0]
    words = [w for w in re.findall(r"[a-z]+", head) if w not in ("gb", "mk", "v")]
    return _WORD_ALIASES.get(words[-1], words[-1]) if words else ""


def _split_norm(norm: str) -> tuple[set[str], set[str]]:
    nums, _, words = norm.partition(" | ")
    return set(nums.split()), set(words.split())


def rank_by_name(query: str, rows: list[dict]) -> list[dict]:
    """Rows matching ``query`` best first (see module docstring)."""
    sku = SKU_RE.search(query or "")
    if sku:
        hit = [r for r in rows if r["sku"].lower() == sku.group(1).lower()]
        if hit:
            return hit
    q_nums, q_words = normalize(query)
    if not q_nums and not q_words:
        return []
    q_noun = head_noun(query)
    scored = []
    for r in rows:
        nums, words = _split_norm(r["norm"])
        if not q_nums <= nums:
            continue
        shared = len(q_words & words)
        if q_words and shared == 0:
            continue
        # Single parts before kits/bundles, then most shared words, same kind
        # of thing (head noun), fewest unmatched words, shortest name.
        key = (
            r.get("type") == "other",
            -shared,
            head_noun(r["name"]) != q_noun,
            len(words - q_words),
            len(r["name"]),
        )
        scored.append((key, r))
    scored.sort(key=lambda x: x[0])
    if not scored:
        return []
    best = scored[0][0][:2]
    # Keep only matches as good as the best (no weak tails).
    return [r for key, r in scored if key[:2] == best]


def match_sku(name: str, rows: list[dict]) -> str | None:
    """Best SKU for a part name from someone's CAD, or None."""
    hits = rank_by_name(name, rows)
    return hits[0]["sku"] if hits else None


# ── index ────────────────────────────────────────────────────────────


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def load_parts(conn: sqlite3.Connection, path: Path) -> int:
    conn.executescript("DROP TABLE IF EXISTS parts;" + PARTS_SCHEMA)
    if not path.is_file():
        return 0
    n = 0
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("sku"):
                continue
            conn.execute(
                "INSERT OR IGNORE INTO parts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["sku"],
                    row.get("name") or "",
                    row.get("type") or None,
                    row.get("series") or None,
                    _float(row.get("length_mm")),
                    row.get("dims") or None,
                    row.get("hole_pattern") or None,
                    _float(row.get("mass_g")),
                    _float(row.get("price")),
                    row.get("counts_as") or None,
                    row.get("product_url") or None,
                    row.get("step_url") or None,
                    norm_text(row.get("name") or ""),
                ),
            )
            n += 1
    return n


def find_parts(
    conn: sqlite3.Connection,
    *,
    sku: str | None = None,
    name: str | None = None,
    type: str | None = None,
    series: str | None = None,
    counts_as: str | None = None,
    length_mm: float | None = None,
    length_tol_mm: float = 0.0,
    limit: int = 10,
) -> list[dict]:
    where, args = [], []
    if sku:
        where.append("sku = ?")
        args.append(sku.strip())
    for col, val in (("type", type), ("series", series), ("counts_as", counts_as)):
        if val:
            where.append(f"{col} = ?")
            args.append(str(val))
    if length_mm is not None:
        tol = abs(float(length_tol_mm or 0))
        where.append("length_mm BETWEEN ? AND ?")
        args += [float(length_mm) - tol - 1e-9, float(length_mm) + tol + 1e-9]
    sql = "SELECT * FROM parts" + (" WHERE " + " AND ".join(where) if where else "")
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY sku", args)]
    if name:
        rows = rank_by_name(name, rows)
    elif length_mm is not None:
        rows.sort(key=lambda r: (abs(r["length_mm"] - float(length_mm)), r["sku"]))
    return rows[:limit]


# ── STEP cache ───────────────────────────────────────────────────────


def step_cache_dir() -> Path:
    env = os.environ.get("FUSION_MCP_STEP_CACHE")
    return Path(env).expanduser() if env else Path.home() / ".fusion-mcp" / "step-cache"


def _safe_sku(sku: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sku or ""):
        raise ValueError(f"Bad SKU for a file name: {sku!r}")
    return sku


def cached_step(sku: str) -> Path | None:
    path = step_cache_dir() / f"{_safe_sku(sku)}.step"
    return path if path.is_file() else None


def _pick_step(zf: zipfile.ZipFile, sku: str) -> bytes:
    names = [n for n in zf.namelist() if n.lower().endswith((".step", ".stp"))]
    if not names:
        raise ValueError("The download has no .step/.stp file in it.")
    named = [n for n in names if sku.lower() in n.lower()]
    best = max(named or names, key=lambda n: zf.getinfo(n).file_size)
    return zf.read(best)


def download_step(sku: str, url: str | None, opener=None) -> Path:
    """Download one part's STEP file into the cache (once) and return its path."""
    have = cached_step(sku)
    if have:
        return have
    if not url:
        raise ValueError(f"{sku} has no STEP file listed on goBILDA.")
    opener = opener or (lambda u: urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": USER_AGENT}), timeout=60
    ).read())
    data = opener(url)
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            data = _pick_step(zf, sku)
    if b"ISO-10303" not in data[:200]:
        raise ValueError(f"{url} did not return a STEP file.")
    path = step_cache_dir() / f"{_safe_sku(sku)}.step"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


# ── formatting ───────────────────────────────────────────────────────

_KEY_DIMS = ("diameter_mm", "od_mm", "id_mm", "bore", "teeth", "pitch", "holes",
             "ratio", "rpm", "width_mm", "thickness_mm")


def part_line(p: dict) -> str:
    bits = [p["sku"], p["name"], p.get("type") or "?"]
    if p.get("length_mm") is not None:
        bits.append(f"L={p['length_mm']:g}mm")
    try:
        dims = json.loads(p.get("dims") or "{}")
    except ValueError:
        dims = {}
    shown = [f"{k}={dims[k]}" for k in _KEY_DIMS if k in dims][:3]
    if shown:
        bits.append(", ".join(shown))
    if p.get("mass_g") is not None:
        bits.append(f"{p['mass_g']:g}g")
    if p.get("counts_as") in ("motor", "servo"):
        bits.append(f"counts as {p['counts_as']}")
    step = cached_step(p["sku"]) if p.get("sku") else None
    if step:
        bits.append(f"STEP cached: {step}")
    elif p.get("step_url"):
        bits.append("STEP not cached (download=true)")
    else:
        bits.append("no STEP")
    return " · ".join(bits)
