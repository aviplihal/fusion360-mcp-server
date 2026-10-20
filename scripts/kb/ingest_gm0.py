"""Ingest Game Manual 0 (gm0) into kb/books/gm0/ as searchable sections.

    uv run python scripts/kb/ingest_gm0.py            # fetch + convert changed pages
    uv run python scripts/kb/ingest_gm0.py --force    # rewrite every page
    uv run python scripts/kb/ingest_gm0.py --no-fetch # use the cached clone as is

gm0 (https://github.com/gamemanual0/gm0) is CC BY-NC 2.0; every section keeps
attribution in its `source` field. A sparse shallow clone lives in .cache/gm0
(gitignored, outside kb/ so its README.md is never indexed). Only three
chapters are kept: common-mechanisms, hardware-components, power-and-electronics.

The reStructuredText is converted with a small line-based converter (no
docutils/pandoc): headings, paragraphs, lists, admonitions and tables survive;
figures, images, raw HTML, toctrees and includes are dropped. Each page is split
at its second-level headings into sections of <= MAX_WORDS words (long ones at
third-level headings or paragraph boundaries) and written as
kb/books/gm0/<page-slug>/<NN>-<section-slug>.md.

kb/books/gm0/manifest.json records the gm0 commit and a hash per page, so a
re-run only rewrites pages whose .rst changed. ideas.csv is hand-written and
never touched by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / ".cache" / "gm0"
OUT = REPO / "kb" / "books" / "gm0"
GIT_URL = "https://github.com/gamemanual0/gm0"
CHAPTERS = ("common-mechanisms", "hardware-components", "power-and-electronics")
DOCS = "source/docs"
URL_BASE = "https://gm0.org/en/latest/docs/"
LICENSE = "CC BY-NC 2.0"
MAX_WORDS = 600
MIN_WORDS = 80  # smaller sections are merged into a neighbour

# Page directory -> kb mechanism type (indexed, filterable with kb_search type=).
TYPES = {
    "drivetrains": "drivetrain",
    "holonomic": "drivetrain",
    "tank": "drivetrain",
    "dead-wheels": "drivetrain",
    "linear-motion-guide": "slide",
    "active-intake": "intake",
    "passive-intake-claw": "claw",
    "transfers": "transfer",
    "turrets": "turret",
    "power-transmission": "power_transmission",
    "arms": "arm",
    "linkages": "arm",
}

# ── fetch ────────────────────────────────────────────────────────────


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def fetch() -> None:
    sparse = [f"{DOCS}/{c}" for c in CHAPTERS]
    if not (CACHE / ".git").is_dir():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        git(
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            GIT_URL,
            str(CACHE),
        )
    else:
        git("fetch", "--depth", "1", "origin", "HEAD", cwd=CACHE)
        git("reset", "--hard", "FETCH_HEAD", cwd=CACHE)
    git("sparse-checkout", "set", *sparse, cwd=CACHE)


# ── rst → text ───────────────────────────────────────────────────────

ADORN = set("=-^~\"*#+`'.:_")
DROP_DIRECTIVES = {
    "figure",
    "image",
    "raw",
    "include",
    "toctree",
    "math",
    "contents",
    "youtube",
    "video",
    "code-block",
    "highlight",
}
LABELS = {
    "note": "Note",
    "tip": "Tip",
    "warning": "Warning",
    "attention": "Attention",
    "important": "Important",
    "caution": "Caution",
    "danger": "Danger",
    "hint": "Hint",
}
SUBST = {
    "reg": "®",
    "trade": "™",
    "copy": "©",
    "deg": "°",
    "plusmn": "±",
    "frac14": "1/4",
    "rarr": "→",
}
DIRECTIVE_RE = re.compile(r"^(\s*)\.\.\s+([\w-]+)::\s*(.*)$")
BULLET_RE = re.compile(r"^(\s*)([-*+]|#\.|\d+[.)])\s+(.*)$")


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def block_end(lines: list[str], start: int, base: int) -> int:
    """Index after the indented block that follows lines[start - 1]."""
    j = start
    while j < len(lines) and (not lines[j].strip() or indent_of(lines[j]) > base):
        j += 1
    while j > start and not lines[j - 1].strip():
        j -= 1
    return j


def dedent(lines: list[str]) -> list[str]:
    ind = min((indent_of(ln) for ln in lines if ln.strip()), default=0)
    return [ln[ind:] for ln in lines]


def mark_headings(lines: list[str]) -> list[str]:
    """Replace over/underlined titles with '\\0H<level>\\0title' marker lines."""
    order: list[tuple[str, bool]] = []
    out: list[str] = []
    i = 0

    def is_rule(s: str) -> bool:
        s = s.rstrip()
        return len(s) >= 3 and s[0] in ADORN and set(s) == {s[0]}

    while i < len(lines):
        ln = lines[i]
        over = (
            is_rule(ln)
            and i + 2 < len(lines)
            and is_rule(lines[i + 2])
            and lines[i + 1].strip()
        )
        if over and not ln.startswith(" "):
            key, text, step = (ln[0], True), lines[i + 1].strip(), 3
        elif (
            ln.strip()
            and not ln.startswith(" ")
            and i + 1 < len(lines)
            and is_rule(lines[i + 1])
            and len(lines[i + 1].rstrip()) >= len(ln.rstrip())
            and not is_rule(ln)
        ):
            key, text, step = (lines[i + 1][0], False), ln.strip(), 2
        else:
            out.append(ln)
            i += 1
            continue
        if key not in order:
            order.append(key)
        out += ["", f"\0H{order.index(key) + 1}\0{text.rstrip(':')}", ""]
        i += step
    return out


def glossary(lines: list[str]) -> list[str]:
    """Glossary entries ("Term" + indented definition) → "**Term**: definition"."""
    entries: list[tuple[str, list[str]]] = []
    for ln in dedent(lines):
        if ln.strip() and indent_of(ln) == 0:
            entries.append((ln.strip().strip("*"), []))
        elif entries:
            entries[-1][1].append(ln)
    out: list[str] = []
    for term, body in entries:
        paras: list[list[str]] = [[]]
        for ln in directives(dedent(body)):
            if ln.strip():
                paras[-1].append(ln.strip())
            elif paras[-1]:
                paras.append([])
        paras = [p for p in paras if p]
        first = " ".join(paras[0]) if paras else ""
        out += ["", f"**{term}**: {first}".rstrip()]
        for p in paras[1:]:
            out += ["", *p]
    return out + [""]


def directives(lines: list[str]) -> list[str]:
    """Expand/drop directives and comments, recursively."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = DIRECTIVE_RE.match(ln)
        if not m and not re.match(r"^\s*\.\.(\s|$)", ln):
            out.append(ln)
            i += 1
            continue
        base = indent_of(ln)
        end = block_end(lines, i + 1, base)
        body = lines[i + 1 : end]
        i = end
        if not m:  # comment, link target, substitution definition
            continue
        name, arg = m.group(2), m.group(3).strip()
        if name in DROP_DIRECTIVES or name == "only" and "latex" in arg:
            continue
        # Skip the option list (":width: 10em") right after the directive line.
        k = 0
        while k < len(body) and re.match(r"^\s+:[\w-]+:", body[k]):
            k += 1
        content = dedent(body[k:])
        if name in LABELS and arg:  # ".. note:: text" — the argument is content
            content = [arg, *content]
        if name == "glossary":
            inner = glossary(content)
        else:
            inner = directives(content)
        label = LABELS.get(name)
        if not label and arg and name not in ("only", "tab-set", "table"):
            label = re.sub(r"\s*\(click to expand\)", "", arg, flags=re.I)
        if label and label != "Term":
            first = next((n for n, t in enumerate(inner) if t.strip()), None)
            if first is not None and not inner[first].startswith(
                ("\0", "+", "|", "=", "**")
            ):
                if BULLET_RE.match(inner[first]):
                    inner.insert(first, f"**{label}:**")
                else:
                    inner[first] = f"**{label}:** {inner[first].lstrip()}"
            else:
                inner.insert(0, f"**{label}:**")
        pad = " " * base
        out += [""] + [pad + t if t.strip() else "" for t in inner] + [""]
    return out


def inline(text: str) -> str:
    text = re.sub(
        r":(?:term|doc|ref|abbr|kbd|guilabel):`([^`<]*?)\s*<[^>]*>`", r"\1", text
    )
    text = re.sub(
        r":(?:doc|ref):`([^`]*)`",
        lambda m: m.group(1).rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
        text,
    )
    text = re.sub(r":\w+:`([^`]*)`", r"\1", text)
    text = re.sub(r"`([^`<]+?)\s*<[^>]*>`__?", r"\1", text)
    text = re.sub(r"`([^`]+)`__?", r"\1", text)
    text = re.sub(r"``([^`]+)``", r"`\1`", text)
    text = re.sub(r"\|(\w+)\|", lambda m: SUBST.get(m.group(1), ""), text)
    text = re.sub(r"\s*\[(?:#\w*|\d+)\]_", "", text)
    text = text.replace("\\ ", "").replace("\\", "")
    return text


def grid_table(rows: list[str]) -> list[str]:
    rule = rows[0].strip()
    cols = [n for n, c in enumerate(rule) if c == "+"]
    out, cells = [], [[] for _ in cols[:-1]]
    for ln in rows[1:]:
        s = ln.strip()
        if s.startswith("+"):
            texts = []
            for cell in cells:
                parts: list[str] = []
                for p in (c.strip() for c in cell):
                    if not p:
                        continue
                    if (
                        parts
                        and not re.match(r"[-*]\s", p)
                        and not parts[-1].startswith("**")
                    ):
                        parts[-1] += " " + p
                    else:
                        parts.append(re.sub(r"^[-*]\s+", "", p))
                texts.append("; ".join(parts))
            if any(texts):
                out.append(" | ".join(texts))
            cells = [[] for _ in cols[:-1]]
            continue
        for n in range(len(cols) - 1):
            cells[n].append(s[cols[n] + 1 : cols[n + 1]] if len(s) > cols[n] else "")
    return out


def simple_table(rows: list[str]) -> list[str]:
    rule = rows[0].strip()
    starts = [m.start() for m in re.finditer(r"=+", rule)]
    ind = indent_of(rows[0])
    out = []
    for ln in rows[1:]:
        s = ln[ind:].rstrip()
        if not s or re.fullmatch(r"[= ]+", s):
            continue
        bounds = starts[1:] + [len(s) + 1]
        cells = [s[a:b].strip() for a, b in zip(starts, bounds)]
        out.append(" | ".join(c for c in cells if c))
    return out


def tables(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if re.fullmatch(r"\+[-=+]+\+", s):
            j = i + 1
            while j < len(lines) and lines[j].strip()[:1] in ("+", "|"):
                j += 1
            out += [""] + ["\0T" + r for r in grid_table(lines[i:j])] + [""]
            i = j
        elif re.fullmatch(r"=+( +=+)+", s):
            j, rules = i + 1, 1
            while j < len(lines) and rules < 3:
                if re.fullmatch(r"=+( +=+)+", lines[j].strip()):
                    rules += 1
                elif not lines[j].strip() and rules >= 2:
                    break
                j += 1
            out += [""] + ["\0T" + r for r in simple_table(lines[i:j])] + [""]
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def reflow(lines: list[str]) -> list[str]:
    """Join wrapped lines into paragraphs / list items. Returns blocks."""
    blocks: list[str] = []
    cur: list[str] = []
    cur_indent = 0

    def flush():
        nonlocal cur
        if cur:
            blocks.append(" ".join(cur))
        cur = []

    for n, ln in enumerate(lines):
        if not ln.strip():
            flush()
            continue
        if ln.startswith("\0"):
            flush()
            blocks.append(ln)
            continue
        if re.fullmatch(r"\s*(\.\.|::|\^{3,}|\+{3,})\s*", ln):
            continue
        b = BULLET_RE.match(ln)
        if b:
            flush()
            depth = "  " if indent_of(ln) >= 2 else ""
            cur, cur_indent = [f"{depth}- {b.group(3).strip()}"], indent_of(ln)
            continue
        ind = indent_of(ln)
        nxt = lines[n + 1] if n + 1 < len(lines) else ""
        # Definition list: unindented term line followed by an indented body.
        if (
            (not cur or ind < cur_indent)
            and nxt.strip()
            and indent_of(nxt) > ind
            and not BULLET_RE.match(nxt)
            and len(ln.split()) <= 8
        ):
            flush()
            blocks.append(f"**{ln.strip().rstrip(':')}**:")
            continue
        if (
            cur
            and cur[0].lstrip().startswith("- ")
            and ind <= cur_indent
            and not cur[-1].endswith(":")
        ):
            flush()
        cur.append(ln.strip())
        if not cur[0].lstrip().startswith("- "):
            cur_indent = ind
    flush()
    # Merge a lone "**Term**:" definition label with the paragraph after it.
    merged: list[str] = []
    for blk in blocks:
        if (
            merged
            and re.fullmatch(r"\*\*[^*]+\*\*:", merged[-1])
            and not blk.startswith("\0")
        ):
            merged[-1] = f"{merged[-1]} {blk.lstrip('- ')}"
        else:
            merged.append(blk)
    return [inline(b) for b in merged]


def convert(rst: str) -> list[str]:
    lines = rst.replace("\t", "    ").splitlines()
    lines = mark_headings(lines)
    lines = directives(lines)
    lines = tables(lines)
    blocks = reflow(lines)
    out = []
    for b in blocks:
        if b.lower().startswith("click here to explore this model"):
            continue
        if re.fullmatch(r"\*\*[^*]+:\*\*", b.strip()):  # label with nothing after
            continue
        out.append(b)
    return out


# ── sections ─────────────────────────────────────────────────────────


def slugify(text: str) -> str:
    return (
        re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50].strip("-") or "section"
    )


def words(blocks: list[str]) -> int:
    return sum(len(b.split()) for b in blocks)


def render(blocks: list[str]) -> str:
    out = []
    for b in blocks:
        if b.startswith("\0H"):
            out.append("#" * min(int(b[2]), 4) + " " + b.split("\0")[2])
        elif b.startswith("\0T"):
            out.append(b[2:])
        else:
            out.append(b)
    text = ""
    for prev, b in zip([""] + out, out):
        # tables rows and list items stay on consecutive lines
        tight = (b.lstrip().startswith("- ") and prev.lstrip().startswith("- ")) or (
            " | " in b and " | " in prev
        )
        text += ("\n" if tight else "\n\n") + b
    return text.strip() + "\n"


def sections(blocks: list[str]) -> tuple[str, list[tuple[str, list[str]]]]:
    """Split converted blocks at level-2 headings → (page title, sections)."""
    page_title = ""
    secs: list[tuple[str, list[str]]] = []
    heading, body = "", []
    for b in blocks:
        if b.startswith("\0H1\0") and not page_title:
            page_title = b.split("\0")[2]
            heading = page_title
            continue
        if b.startswith("\0H2\0"):
            secs.append((heading, body))
            heading, body = b.split("\0")[2], []
            continue
        body.append(b)
    secs.append((heading, body))
    # Fold tiny sections ("Advantages", a two-line intro) into a neighbour.
    merged: list[tuple[str, list[str]]] = []
    for h, body in secs:
        if words([b for b in body if not b.startswith("\0H")]) == 0:
            continue
        if merged:
            ph, pb = merged[-1]
            small = min(words(pb), words(body)) < MIN_WORDS
            if small and words(pb) + words(body) <= MAX_WORDS:
                merged[-1] = (ph, pb + [f"\0H2\0{h}"] + body)
                continue
        merged.append((h, body))
    out = []
    for h, body in merged:
        out.extend(split_long(h, body))
    return page_title, out


def split_long(heading: str, body: list[str]) -> list[tuple[str, list[str]]]:
    if words(body) <= MAX_WORDS:
        return [(heading, body)]
    chunks: list[list[str]] = [[]]
    for b in body:
        cur = chunks[-1]
        starts_sub = b.startswith("\0H") and words(cur) > MAX_WORDS // 3
        if cur and (starts_sub or words(cur) + len(b.split()) > MAX_WORDS):
            chunks.append([])
        chunks[-1].append(b)
    out = []
    for n, chunk in enumerate(chunks):
        sub = next((b.split("\0")[2] for b in chunk if b.startswith("\0H")), None)
        if n == 0:
            title = heading
        elif sub and chunk[0].startswith("\0H"):
            title = f"{heading} – {sub}"
        else:
            title = f"{heading} (cont.)"
        out.append((title, chunk))
    return out


# ── pages ────────────────────────────────────────────────────────────


def page_list(docs: Path) -> list[Path]:
    return sorted(p for c in CHAPTERS for p in (docs / c).rglob("*.rst"))


def page_slugs(pages: list[Path], docs: Path) -> dict[Path, str]:
    def parts(p: Path) -> list[str]:
        ps = list(p.relative_to(docs).with_suffix("").parts)
        return ps[:-1] if ps[-1] == "index" and len(ps) > 1 else ps

    last = [parts(p)[-1] for p in pages]
    slugs = {}
    for p in pages:
        ps = parts(p)
        dup = last.count(ps[-1]) > 1 and len(ps) > 1
        slugs[p] = "-".join(ps[-2:]) if dup else ps[-1]
    return slugs


def page_type(rel: Path) -> str | None:
    for part in reversed(rel.with_suffix("").parts):
        if part in TYPES:
            return TYPES[part]
    return None


def write_page(path: Path, docs: Path, slug: str, commit: str) -> tuple[int, int]:
    rel = path.relative_to(docs)
    page_title, secs = sections(convert(path.read_text(encoding="utf-8")))
    page_title = page_title or slug.replace("-", " ").title()
    url = URL_BASE + rel.with_suffix(".html").as_posix()
    kind = page_type(rel)
    out_dir = OUT / slug
    if out_dir.exists():
        shutil.rmtree(out_dir)
    total = 0
    for n, (heading, body) in enumerate(secs, 1):
        if heading == page_title:
            title = page_title
        elif len(heading.split()) <= 4 and page_title.lower() not in heading.lower():
            title = f"{page_title}: {heading}"
        else:
            title = heading
        sec_slug = slugify(heading if n > 1 or heading != page_title else "intro")
        fm = [
            "---",
            f"id: {slug}/{n:02d}",
            f"title: {title}",
            f"page: {page_title}",
        ]
        if kind:
            fm.append(f"type: {kind}")
        fm += [f"source: gm0 {commit[:12]}, {LICENSE}", f"url: {url}", "---", "", ""]
        text = render(body)
        total += len(text.split())
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{n:02d}-{sec_slug}.md").write_text(
            "\n".join(fm) + text, encoding="utf-8"
        )
    return len(secs), total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true", help="rewrite every page")
    ap.add_argument("--no-fetch", action="store_true", help="use the cached clone")
    args = ap.parse_args()
    if not args.no_fetch:
        fetch()
    commit = git("rev-parse", "HEAD", cwd=CACHE)
    docs = CACHE / DOCS
    pages = page_list(docs)
    slugs = page_slugs(pages, docs)

    manifest_path = OUT / "manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    old_pages = old.get("pages", {})
    new_pages: dict[str, dict] = {}
    changed = 0
    for p in pages:
        slug = slugs[p]
        digest = hashlib.sha1(p.read_bytes()).hexdigest()[:16]
        prev = old_pages.get(slug)
        if not args.force and prev and prev["sha"] == digest and (OUT / slug).is_dir():
            new_pages[slug] = prev
            continue
        n_secs, n_words = write_page(p, docs, slug, commit)
        new_pages[slug] = {
            "file": p.relative_to(docs).as_posix(),
            "sha": digest,
            "commit": commit[:12],
            "sections": n_secs,
            "words": n_words,
        }
        changed += 1
    for slug in set(old_pages) - set(new_pages):
        shutil.rmtree(OUT / slug, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "repo": GIT_URL,
        "commit": commit,
        "license": LICENSE,
        "pages": new_pages,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    secs = sum(v["sections"] for v in new_pages.values())
    wds = sum(v["words"] for v in new_pages.values())
    print(
        f"gm0 {commit[:12]}: {len(new_pages)} pages ({changed} rewritten), "
        f"{secs} sections, {wds} words"
    )


if __name__ == "__main__":
    main()
