"""Knowledge base index: markdown/CSV files in ``kb/`` → a throwaway SQLite index.

The files are the source of truth (see docs/plans/knowledge-base.md). The index
lives at ``kb/.index.sqlite`` and is rebuilt whenever any indexed file changes,
so it never needs migrating: delete it and it comes back.

Indexed:
  robots/<robot-id>/robot.md        kind=robot      id = frontmatter id
  robots/<robot-id>/<key>.md        kind=mechanism  id = <robot-id>/<key>
  books/<book>/rules/<ID>.md        kind=rule       id = frontmatter id (R105)
  books/<book>/**/<name>.md         kind=book       id = <book>/<frontmatter id or name>
  ideas.csv                         kind=idea       id = csv id
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

KINDS = ("robot", "mechanism", "idea", "rule", "book")
# Bump when parsing or the schema changes, so existing indexes rebuild.
INDEX_VERSION = "3"

# Words teams use for the same thing. Each group expands to all its members.
SYNONYMS = [
    {"shooter", "launcher", "flywheel"},
    {"intake", "collector"},
    {"slide", "slides", "lift", "elevator", "extension"},
    {"viper", "linear slide"},
    {"claw", "gripper", "grabber"},
    {"transfer", "indexer", "conveyor"},
    {"pto", "power transmission", "differential"},
    {"drivetrain", "chassis", "drive"},
    {"hang", "climb", "ascent"},
    {"odometry", "odo", "dead wheel", "deadwheel"},
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "how",
    "in",
    "is",
    "it",
    "many",
    "much",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "which",
    "with",
}

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
# Kept as text even when they look like numbers ("9.10" must not become 9.1).
_TEXT_KEYS = {"id", "title", "name", "type", "season", "source"}
_WORD_RE = re.compile(r"[A-Za-z0-9]+")

_SCHEMA = """
CREATE TABLE docs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    type TEXT,
    season TEXT,
    team TEXT,
    multiplier REAL NOT NULL DEFAULT 1.0,
    weight REAL NOT NULL DEFAULT 0,
    ours INTEGER NOT NULL DEFAULT 0,
    parent TEXT,
    path TEXT NOT NULL,
    meta TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE VIRTUAL TABLE fts USING fts5(
    id UNINDEXED, title, body, tags, tokenize='porter unicode61'
);
CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT);
"""


def default_kb_dir() -> Path:
    """``$FUSION_MCP_KB_DIR``, else ``kb/`` at the repo root (editable install)."""
    env = os.environ.get("FUSION_MCP_KB_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2] / "kb"


# ── parsing ──────────────────────────────────────────────────────────


def _parse_value(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        pass
    if raw.startswith("[") and raw.endswith("]"):
        return [v.strip() for v in raw[1:-1].split(",") if v.strip()]
    return raw


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split ``---`` frontmatter (``key: value`` lines, JSON values allowed)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            key, _, raw = line.partition(":")
            key = key.strip()
            value = _parse_value(raw)
            if key in _TEXT_KEYS and not isinstance(value, (dict, list)):
                value = raw.strip() or None
            meta[key] = value
    return meta, text[m.end() :]


def _team_text(team) -> str | None:
    if isinstance(team, dict):
        parts = [str(team.get("number") or ""), team.get("name") or ""]
        return " ".join(p for p in parts if p) or None
    return str(team) if team else None


def _facet_tags(meta: dict) -> str:
    facets = meta.get("facets") if isinstance(meta.get("facets"), dict) else {}
    return " ".join(str(v) for v in facets.values() if v not in (None, ""))


def _doc_from_markdown(path: Path, rel: Path) -> dict | None:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    parts = rel.parts
    if parts[0] == "robots" and len(parts) == 3:
        robot_id = parts[1]
        if rel.name == "robot.md":
            kind, doc_id, parent = "robot", meta.get("id") or robot_id, None
        else:
            kind, doc_id, parent = "mechanism", f"{robot_id}/{rel.stem}", robot_id
    elif parts[0] == "books" and len(parts) >= 3:
        book = parts[1]
        if "rules" in parts[2:-1]:
            kind, doc_id = "rule", str(meta.get("id") or rel.stem)
        else:
            kind, doc_id = "book", f"{book}/{meta.get('id') or rel.stem}"
        parent = book
    else:
        return None
    # robot.md is always the robot card; a mechanism-only source entry says so
    # in `entry`, not `kind`.
    rating = meta.get("rating") if isinstance(meta.get("rating"), dict) else {}
    source = meta.get("source")
    site = source.get("site") if isinstance(source, dict) else source
    ours = site == "ours"
    title = str(meta.get("title") or meta.get("name") or doc_id)
    return {
        "id": doc_id,
        "kind": kind,
        "title": title,
        "type": meta.get("type"),
        "season": meta.get("season"),
        "team": _team_text(meta.get("team")),
        "multiplier": float(rating.get("multiplier") or meta.get("multiplier") or 1.0),
        "weight": 0.0,
        "ours": int(bool(ours)),
        "parent": parent,
        "path": str(rel),
        "meta": meta,
        "body": body.strip(),
        "tags": " ".join(
            filter(
                None,
                [
                    str(meta.get("type") or ""),
                    _facet_tags(meta),
                    _team_text(meta.get("team")) or "",
                ],
            )
        ),
    }


def _docs_from_ideas(path: Path, rel: Path) -> list[dict]:
    docs = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seen = [s for s in (row.get("seen_in") or "").split(";") if s.strip()]
            docs.append(
                {
                    "id": row["id"],
                    "kind": "idea",
                    "title": row["text"],
                    "type": row.get("mechanism") or None,
                    "season": None,
                    "team": None,
                    "multiplier": 1.0,
                    "weight": float(len(seen)),
                    "ours": 0,
                    "parent": None,
                    "path": str(rel),
                    "meta": {
                        "seen_in": seen,
                        "source": row.get("source") or None,
                        "tags": row.get("tags") or None,
                    },
                    "body": row["text"],
                    "tags": " ".join(
                        filter(None, [row.get("mechanism"), row.get("tags")])
                    ),
                }
            )
    return docs


def _indexed_files(kb_dir: Path) -> list[Path]:
    files = []
    for sub in ("robots", "books"):
        root = kb_dir / sub
        if root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    ideas = kb_dir / "ideas.csv"
    if ideas.is_file():
        files.append(ideas)
    return files


def _signature(files: list[Path]) -> str:
    h = hashlib.sha1(f"v{INDEX_VERSION}\n".encode())
    for f in files:
        st = f.stat()
        h.update(f"{f}\0{st.st_mtime_ns}\0{st.st_size}\n".encode())
    return h.hexdigest()


def current_season(kb_dir: Path) -> str | None:
    """Newest ``kb/rules/<season>/`` folder, e.g. ``2026-27``."""
    rules = kb_dir / "rules"
    seasons = (
        sorted(p.name for p in rules.iterdir() if p.is_dir()) if rules.is_dir() else []
    )
    return seasons[-1] if seasons else None


# ── index ────────────────────────────────────────────────────────────


class KnowledgeBase:
    def __init__(self, kb_dir: Path | str | None = None):
        self.kb_dir = Path(kb_dir) if kb_dir else default_kb_dir()
        self.index_path = self.kb_dir / ".index.sqlite"
        self._conn: sqlite3.Connection | None = None
        self._signature: str | None = None

    def _connect(self) -> sqlite3.Connection:
        if not self.kb_dir.is_dir():
            raise FileNotFoundError(
                f"Knowledge base folder not found: {self.kb_dir}. "
                "Set FUSION_MCP_KB_DIR to the repo's kb/ folder."
            )
        files = _indexed_files(self.kb_dir)
        sig = _signature(files)
        if self._conn is not None and sig == self._signature:
            return self._conn
        conn = self._conn or sqlite3.connect(self.index_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            stored = conn.execute(
                "SELECT value FROM info WHERE key='signature'"
            ).fetchone()
        except sqlite3.OperationalError:
            stored = None
        if not stored or stored[0] != sig:
            self._rebuild(conn, files, sig)
        self._conn, self._signature = conn, sig
        return conn

    def _rebuild(self, conn: sqlite3.Connection, files: list[Path], sig: str) -> None:
        conn.executescript(
            "DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS fts;"
            " DROP TABLE IF EXISTS info;" + _SCHEMA
        )
        docs: list[dict] = []
        for f in files:
            rel = f.relative_to(self.kb_dir)
            if f.suffix == ".csv":
                docs.extend(_docs_from_ideas(f, rel))
            else:
                doc = _doc_from_markdown(f, rel)
                if doc:
                    docs.append(doc)
        seen: set[str] = set()
        for d in docs:
            if d["id"] in seen:
                continue
            seen.add(d["id"])
            conn.execute(
                "INSERT INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    d["id"],
                    d["kind"],
                    d["title"],
                    d["type"],
                    d["season"],
                    d["team"],
                    d["multiplier"],
                    d["weight"],
                    d["ours"],
                    d["parent"],
                    d["path"],
                    json.dumps(d["meta"], ensure_ascii=False),
                    d["body"],
                ),
            )
            conn.execute(
                "INSERT INTO fts VALUES (?,?,?,?)",
                (d["id"], d["title"], d["body"], d["tags"]),
            )
        conn.execute("INSERT INTO info VALUES ('signature', ?)", (sig,))
        conn.commit()

    # ── queries ──────────────────────────────────────────────────────

    def search(
        self,
        query: str = "",
        *,
        kind: str | None = None,
        type: str | None = None,
        season: str | None = None,
        facets: dict | None = None,
        limit: int = 8,
    ) -> list[dict]:
        conn = self._connect()
        where, args = [], []
        if kind:
            where.append("d.kind = ?")
            args.append(kind)
        if type:
            where.append("d.type = ?")
            args.append(type)
        if season:
            where.append("d.season LIKE ?")
            args.append(f"%{season}%")
        for key, value in (facets or {}).items():
            if not re.fullmatch(r"[A-Za-z0-9_]+", key):
                raise ValueError(f"Bad facet name: {key!r}")
            where.append(f"json_extract(d.meta, '$.facets.{key}') = ?")
            args.append(value)

        season_now = current_season(self.kb_dir) or ""
        boost = (
            "d.multiplier"
            " * (CASE WHEN d.ours THEN 1.2 ELSE 1 END)"
            " * (CASE WHEN ? != '' AND d.season LIKE ? THEN 1.1 ELSE 1 END)"
            " * (1 + 0.15 * ln(1 + d.weight))"
        )
        boost_args = [season_now, f"{season_now}%"]
        match = fts_query(query)
        if match:
            sql = (
                f"SELECT d.*, snippet(fts, 2, '', '', '…', 12) AS snip, "
                f"bm25(fts, 3.0, 1.0, 2.0) * {boost} AS score "
                "FROM fts JOIN docs d ON d.id = fts.id WHERE fts MATCH ?"
                + "".join(f" AND {w}" for w in where)
                + " ORDER BY score LIMIT ?"
            )
            params = boost_args + [match] + args + [limit]
        else:
            sql = (
                f"SELECT d.*, NULL AS snip, -{boost} AS score FROM docs d"
                + (" WHERE " + " AND ".join(where) if where else "")
                + " ORDER BY score, d.id LIMIT ?"
            )
            params = boost_args + args + [limit]
        return [_row_dict(r) for r in conn.execute(sql, params)]

    def get(self, doc_id: str) -> dict | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT *, NULL AS snip FROM docs WHERE id = ? COLLATE NOCASE", (doc_id,)
        ).fetchone()
        if not row:
            return None
        doc = _row_dict(row)
        if doc["kind"] == "robot":
            doc["children"] = [
                _row_dict(r)
                for r in conn.execute(
                    "SELECT *, NULL AS snip FROM docs WHERE parent = ? AND kind = "
                    "'mechanism' ORDER BY id",
                    (doc["id"],),
                )
            ]
        return doc

    def similar_ids(self, doc_id: str, limit: int = 5) -> list[str]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT id FROM docs WHERE id LIKE ? ORDER BY length(id) LIMIT ?",
            (f"%{doc_id}%", limit),
        ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict[str, int]:
        conn = self._connect()
        return {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT kind, count(*) FROM docs GROUP BY kind ORDER BY kind"
            )
        }


def fts_query(query: str) -> str:
    """Turn free text into an FTS5 OR query with synonyms and prefix matching."""
    text = (query or "").lower()
    terms: list[str] = []
    for word in _WORD_RE.findall(text):
        if word in STOPWORDS:
            continue
        group = next((g for g in SYNONYMS if word in g), {word})
        for term in sorted(group):
            for w in _WORD_RE.findall(term):
                token = f'"{w}"*' if len(w) > 2 else f'"{w}"'
                if token not in terms:
                    terms.append(token)
    for group in SYNONYMS:
        for phrase in group:
            if " " in phrase and phrase in text:
                for alt in sorted(group):
                    token = f'"{alt}"'
                    if token not in terms:
                        terms.append(token)
    return " OR ".join(terms)


def _row_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["meta"] = json.loads(d["meta"])
    return d
