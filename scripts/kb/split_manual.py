"""Split the FTC competition manual PDF into one markdown file per rule (R, G, I)
plus one per heading for the field and scoring sections (9, 10).

Usage: uv run --with pypdf python -I scripts/kb/split_manual.py <manual.pdf> <out_dir>
Re-run on each team update (TU06, ...); the out_dir is replaced.
"""

import re
import shutil
import sys
from pathlib import Path

from pypdf import PdfReader

KEEP_RULES = ("R", "G", "I")
KEEP_SECTIONS = ("9", "10", "12")  # field, scoring, robot construction intro (COTS/VENDOR definitions)

RULE_RE = re.compile(r"^ ?([A-Z]{1,2})(\d{3}) \*?(.*)$")
HEADING_RE = re.compile(r"^ ?(\d{1,2})\.(\d{1,2}(?:\.\d{1,2})?) +([A-Z][^.]{2,80})$")
TOP_HEADING_RE = re.compile(r"^ ?(\d{1,2}) ([A-Z][A-Za-z&/ ]{3,45}(?: \([A-Z]+\))?)\s*$")
NOISE_RE = re.compile(
    r"^\s*$|^Version: |^Section \d+ |^Rules \([A-Z]+\)\s*$|^\s*\d+ of \d+\s*$|^Figure \d+-\d+:\s*$"
)
BULLET_RE = re.compile(r"^(?:[A-Z]\. |[−•–-] |\d+\. )")


def pages(pdf_path):
    for i, page in enumerate(PdfReader(pdf_path).pages, start=1):
        yield i, (page.extract_text() or "").splitlines()


def to_paragraphs(lines):
    """Join wrapped PDF lines; keep list items on their own lines."""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out and not BULLET_RE.match(line) and not out[-1].endswith((".", ":", ")")):
            out[-1] += " " + line
        else:
            out.append(line)
    return "\n".join(out).replace("  ", " ")


def split(pdf_path, out_dir, version):
    chunks = []  # {kind, id, title, page, lines}
    current = None
    in_toc = True
    for page_no, lines in pages(pdf_path):
        if page_no > 4:
            in_toc = False
        for line in lines:
            if in_toc or NOISE_RE.match(line):
                continue
            rule = RULE_RE.match(line)
            heading = HEADING_RE.match(line)
            top = None if heading else TOP_HEADING_RE.match(line)
            if top:
                current = {"kind": "section", "section": top[1], "id": top[1],
                           "title": top[2].strip(), "page": page_no, "lines": []}
                chunks.append(current)
            elif rule:
                current = {"kind": "rule", "prefix": rule[1], "id": rule[1] + rule[2],
                           "title": rule[3].strip(), "page": page_no, "lines": [rule[3]]}
                chunks.append(current)
            elif heading:
                current = {"kind": "section", "section": heading[1],
                           "id": f"{heading[1]}.{heading[2]}", "title": heading[3].strip(),
                           "page": page_no, "lines": []}
                chunks.append(current)
            elif current:
                current["lines"].append(line)

    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "rules").mkdir(parents=True)
    (out / "sections").mkdir()

    written = {"rules": 0, "sections": 0}
    seen = set()
    for c in chunks:
        if c["kind"] == "rule":
            if c["prefix"] not in KEEP_RULES or c["id"] in seen:
                continue
            seen.add(c["id"])
            # The rule's short title is its first sentence.
            title = re.split(r"(?<=\.) ", c["title"], maxsplit=1)[0]
            path = out / "rules" / f"{c['id']}.md"
            written["rules"] += 1
        else:
            if c["section"] not in KEEP_SECTIONS:
                continue
            title = c["title"]
            path = out / "sections" / f"{c['id']}.md"
            written["sections"] += 1
        body = to_paragraphs(c["lines"])
        path.write_text(
            f"---\nid: {c['id']}\ntitle: {title}\npage: {c['page']}\n"
            f"source: BIOBUZZ competition manual {version}\n---\n\n{body}\n"
        )
    return written


if __name__ == "__main__":
    pdf, out_dir = sys.argv[1], sys.argv[2]
    version = re.search(r"TU\d+", Path(pdf).name)
    print(split(pdf, out_dir, version[0] if version else "unknown"))
