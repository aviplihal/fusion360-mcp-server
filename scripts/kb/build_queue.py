"""Build kb/ingest/queue.csv from FTC CAD Base and Open Vault.

robot-ingest-brief step 0.

Usage: python3 -I scripts/kb/build_queue.py [--repo DIR]
Keeps the status/note of rows already in queue.csv, so it is safe to re-run.
"""

import argparse
import csv
import html
import json
import re
import urllib.request
from pathlib import Path

CADBASE = "https://www.cadbaseftc.com"
OPEN_VAULT = "https://www.open-vault-ftc.org/cad/"
OV_CATEGORIES = [
    "robots",
    "drivetrains",
    "active-intakes",
    "claws",
    "outtakes",
    "dead-axles",
    "power-transmissions",
]
FIELDS = [
    "id",
    "site",
    "title",
    "kind",
    "category",
    "season",
    "team_number",
    "platform",
    "url",
    "onshape_doc",
    "status",
    "note",
]

# Season name -> (start year, canonical label). Start year = FTC Scout season year.
SEASONS = {
    "biobuzz": (2026, "2026-27 BIOBUZZ"),
    "decode": (2025, "2025-26 DECODE"),
    "into the deep": (2024, "2024-25 INTO THE DEEP"),
    "centerstage": (2023, "2023-24 CENTERSTAGE"),
    "power play": (2022, "2022-23 POWERPLAY"),
    "powerplay": (2022, "2022-23 POWERPLAY"),
    "freight frenzy": (2021, "2021-22 FREIGHT FRENZY"),
    "ultimate goal": (2020, "2020-21 ULTIMATE GOAL"),
    "skystone": (2019, "2019-20 SKYSTONE"),
}
UNSPECIFIED = "Unspecified / Offseason"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def season_label(text):
    t = (text or "").lower()
    for key, (_, label) in SEASONS.items():
        if key in t:
            return label
    return UNSPECIFIED


def onshape_doc(url):
    m = re.search(r"cad\.onshape\.com/documents/([0-9a-f]{24})", url or "")
    return m.group(1) if m else ""


def platform(url, declared=""):
    if "onshape.com" in (url or ""):
        return "Onshape"
    for host, name in (
        ("drive.google", "Google Drive"),
        ("grabcad", "GrabCAD"),
        ("autodesk", "Fusion"),
        ("a360", "Fusion"),
    ):
        if host in (url or ""):
            return name
    return declared or "other"


def cadbase_rows(page):
    strings = [
        json.loads('"' + s + '"')
        for s in re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', page)
    ]
    text = "".join(strings)
    dec, seen = json.JSONDecoder(), {}
    for m in re.finditer(r'\{"id":"', text):
        try:
            o, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(o, dict) and "url" in o and ("program" in o or "season" in o):
            seen.setdefault(o["id"], o)
    rows = []
    for o in seen.values():
        if o.get("program") != "FTC" or o.get("kind") != "cad":
            continue
        url = o["url"]
        doc = onshape_doc(url)
        cat = o.get("primaryCategory") or ""
        rows.append(
            {
                "id": f"cb-{doc}" if doc else f"cb-{o['id']}",
                "site": "FTC CAD Base",
                "title": o.get("title", ""),
                "kind": "robot" if cat == "Full Robot" else "mechanism",
                "category": cat,
                "season": season_label(o.get("season")),
                "team_number": "",
                "platform": platform(url, o.get("cadPlatform", "")),
                "url": url,
                "onshape_doc": doc,
                "status": "",
                "note": "",
            }
        )
    return rows


def ov_field(block, label):
    m = re.search(r"<strong>" + label + r":</strong>\s*(.*?)</p>", block, re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split() if m else []


def open_vault_rows(category, page):
    rows = []
    for block in page.split('class="portfolio-modal modal fade"')[1:]:
        title = re.search(r'<h2 class="fw-bolder">(.*?)</h2>', block, re.S)
        link = re.search(r'href="([^"]+)"[^>]*\s+class="onshape-button-link"', block)
        if not title or not link:
            continue
        url = html.unescape(link.group(1))
        doc = onshape_doc(url)
        team = " ".join(ov_field(block, "Team Number"))
        seasons = " ".join(ov_field(block, "Seasons used"))
        used = " ".join(ov_field(block, "Used in Competition"))
        rows.append(
            {
                "id": f"ov-{doc}"
                if doc
                else "ov-"
                + re.sub(r"[^a-z0-9]+", "-", title.group(1).lower()).strip("-"),
                "site": "Open Vault",
                "title": html.unescape(title.group(1).strip()),
                "kind": "robot" if category == "robots" else "mechanism",
                "category": category,
                "season": season_label(seasons),
                "team_number": team if team.isdigit() else "",
                "platform": platform(url),
                "url": url,
                "onshape_doc": doc,
                "status": "",
                "note": f"used in competition: {used}" if used else "",
            }
        )
    return rows


def sort_key(r):
    label = r["season"]
    year = next((y for y, lab in SEASONS.values() if lab == label), 0)
    if label == UNSPECIFIED:
        group = 9
    elif year == 2026:
        group = 0
    elif year == 2025:
        group = 1
    else:
        group = 2
    return (group, -year, r["kind"] != "robot", r["title"].lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()
    out = Path(args.repo) / "kb/ingest/queue.csv"

    rows = cadbase_rows(fetch(CADBASE))
    ov = []
    for c in OV_CATEGORIES:
        ov += open_vault_rows(c, fetch(OPEN_VAULT + c))

    # Same Onshape doc on both sites -> one row; prefer Open Vault (has team number).
    by_doc = {r["onshape_doc"]: r for r in ov if r["onshape_doc"]}
    merged = list(ov)
    for r in rows:
        twin = by_doc.get(r["onshape_doc"]) if r["onshape_doc"] else None
        if twin:
            twin["note"] = "; ".join(
                filter(None, [twin["note"], f"also on FTC CAD Base ({r['title']})"])
            )
            if twin["season"] == UNSPECIFIED:
                twin["season"] = r["season"]
        else:
            merged.append(r)

    # Several entries pointing at one doc: keep the first.
    uniq = {}
    for r in merged:
        uniq.setdefault(r["id"], r)
    merged = sorted(uniq.values(), key=sort_key)

    old = {}
    if out.exists():
        with out.open() as f:
            old = {r["id"]: r for r in csv.DictReader(f)}
    for r in merged:
        if r["id"] in old and old[r["id"]]["status"]:
            r["status"], r["note"] = old[r["id"]]["status"], old[r["id"]]["note"]
        elif not r["status"]:
            r["status"] = (
                "queued"
                if r["platform"] == "Onshape" and r["onshape_doc"]
                else "skipped-non-onshape"
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(merged)
    counts = {}
    for r in merged:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{len(merged)} rows -> {out}  {counts}")


if __name__ == "__main__":
    main()
