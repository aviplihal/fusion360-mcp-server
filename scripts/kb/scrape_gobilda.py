"""Scrape goBILDA's catalog into kb/parts/parts.csv.

Source: the store's category pages. Each one embeds its product list as JSON
(``window.jsContext``) with sku, name, price, categories and custom fields
(spec_Weight, filter_*, download_STEP File), up to 100 products per page, so
~400 requests cover the whole catalog. Product pages are never fetched.

Politeness: robots.txt (checked 2026-10-20) allows category pages and asks AI
agents for a 10 s crawl delay; goBILDA has no terms of use page. One request at
a time, DELAY seconds apart, raw responses cached gzipped in kb/parts/.cache/
so a rerun (or ``--offline``) costs no requests.

    uv run python scripts/kb/scrape_gobilda.py            # fetch missing + build
    uv run python scripts/kb/scrape_gobilda.py --offline  # rebuild CSV from cache
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://www.gobilda.com"
SITEMAP = BASE + "/xmlsitemap.php?type=categories&page=1"
DELAY = 10.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "fusion360-mcp-kb/0.1 (FTC team parts index; one request per 10 s)"
)
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "kb" / "parts" / ".cache"
OUT = ROOT / "kb" / "parts" / "parts.csv"

FIELDS = [
    "sku",
    "name",
    "type",
    "series",
    "length_mm",
    "dims",
    "hole_pattern",
    "mass_g",
    "price",
    "counts_as",
    "product_url",
    "step_url",
]

_last_request = 0.0


# ── fetching ─────────────────────────────────────────────────────────


def _cache_path(url: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", url.removeprefix(BASE)).strip("-")[:80]
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    return CACHE / f"{slug or 'root'}-{digest}.html.gz"


def fetch(url: str, offline: bool = False) -> str | None:
    """Cached GET. Returns None when offline and not cached, or on HTTP error."""
    global _last_request
    path = _cache_path(url)
    if path.is_file():
        return gzip.decompress(path.read_bytes()).decode("utf-8")
    if offline:
        return None
    wait = DELAY - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - log and keep going
        print(f"  ! {url}: {exc}", file=sys.stderr)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(text.encode("utf-8")))
    return text


_CTX_RE = re.compile(r'window\.jsContext = JSON\.parse\(("(?:[^"\\]|\\.)*")\);')


def page_context(text: str) -> dict:
    m = _CTX_RE.search(text or "")
    return json.loads(json.loads(m.group(1))) if m else {}


def category_urls(offline: bool) -> list[str]:
    xml = fetch(SITEMAP, offline) or ""
    urls = [html.unescape(u) for u in re.findall(r"<loc>([^<]+)</loc>", xml)]
    return [u for u in urls if "/merch" not in u]


def crawl(offline: bool) -> dict[str, dict]:
    """sku → product dict (merged over every category page it appears on)."""
    products: dict[str, dict] = {}
    urls = category_urls(offline)
    for i, url in enumerate(urls, 1):
        page = 1
        while True:
            page_url = url if page == 1 else f"{url}?page={page}"
            ctx = page_context(fetch(page_url, offline) or "")
            cat = ctx.get("category") or {}
            items = cat.get("products") or []
            for p in items:
                sku = (p.get("sku") or "").strip()
                if not sku:
                    continue
                known = products.setdefault(sku, p)
                cats = set(known.get("category") or []) | set(p.get("category") or [])
                known["category"] = sorted(cats)
            total = int(cat.get("total_products") or 0)
            per_page = int(ctx.get("categoryProductsPerPage") or 100)
            if not items or page * per_page >= total:
                break
            page += 1
        if i % 25 == 0:
            print(f"  {i}/{len(urls)} categories, {len(products)} products")
    return products


# ── parsing ──────────────────────────────────────────────────────────


def clean(text: str) -> str:
    text = html.unescape(text or "").replace("®", "").replace("™", "")
    return re.sub(r"\s+", " ", text).strip()


def _num(s: str):
    v = float(s)
    return int(v) if v.is_integer() else v


# Order matters: first rule whose pattern matches the name (then categories) wins.
_TYPE_RULES = [
    ("other", r"\bkit\b|\bbundle\b|\bassortment\b"),
    ("motor", r"^\d{4} series yellow jacket (planetary gear )?motor\b"),
    ("motor", r"^\d{4} series .*\bmotor\b(?!.*(mount|bracket|cable|plate|clamp))"),
    ("servo", r"servo(?!.*(hub|horn|block|plate|mount|bracket|cable|extension|"
     r"programmer|tester|spline|arm|gearbox kit|coupler|case|gear\b|saver))"),
    ("electronics", r"\b(battery|cable|wire|controller|sensor|switch|camera|"
     r"connector|adaptor|adapter|fuse|charger|receiver|transmitter|bec|led|"
     r"light|odometry pod|pinpoint|encoder|harness|lead\b)"),
    ("channel", r"\bchannel\b|\bgorail\b|\bgotube\b"),
    ("gear", r"\bgear\b(?!box)|\bpinion\b|\bworm\b"),
    ("pulley", r"\bpulley\b"),
    ("sprocket", r"\bsprocket\b"),
    ("wheel", r"\bwheel\b|\btire\b|\bomni\b|\bmecanum\b"),
    ("bearing", r"\bbearing\b|\bpillow block\b"),
    ("hub", r"\bhub\b"),
    ("shaft", r"\bshaft(ing)?\b(?!.*(spacer|collar|coupler|beam))|\btube\b|"
     r"\btubing\b|\brod\b"),
    ("spacer", r"\bspacer\b|\bstandoff\b|\bshim\b|\bcollar\b"),
    ("hardware", r"\bscrew\b|\bnut\b|\bwasher\b|\bbolt\b|\bspring\b|\bmagnet\b|"
     r"\bcinch\b|\bgrommet\b|\bthread locker\b|\blubricant\b|\bcoupler\b"),
    ("bracket", r"\bbracket\b|\bmount\b|\bbeam\b|\bplate\b|\bblock\b|"
     r"\bgusset\b|\bhinge\b|\badaptor\b|\bbaseplate\b|\bcap\b"),
]
_TYPE_RES = [(t, re.compile(p, re.I)) for t, p in _TYPE_RULES]

# Category-path fallbacks for names the rules miss.
_CATEGORY_TYPES = [
    ("MOTION/Motors", "motor"),
    ("MOTION/Servos", "servo"),
    ("ELECTRONICS", "electronics"),
    ("HARDWARE", "hardware"),
    ("STRUCTURE/Channel", "channel"),
    ("STRUCTURE", "bracket"),
]


def classify(name: str, categories: list[str]) -> str:
    for t, rx in _TYPE_RES:
        if rx.search(name):
            return t
    for prefix, t in _CATEGORY_TYPES:
        if any(c.startswith(prefix) for c in categories):
            return t
    return "other"


def counts_as(ptype: str) -> str:
    return ptype if ptype in ("motor", "servo") else "none"


_DIM_PATTERNS = [
    ("holes", r"(\d+) Hole"),
    ("grid_holes", r"(\d+ x \d+) Hole"),
    ("bore", r"(\d+(?:\.\d+)?mm (?:REX|D|Round|Hex|Square)|1/2\" Hex|"
     r"\d+/\d+\" (?:Round|Hex|D))(?: Bore)?"),
    ("teeth", r"(\d+) Tooth"),
    ("od_mm", r"(\d+(?:\.\d+)?)mm OD"),
    ("id_mm", r"(\d+(?:\.\d+)?)mm ID"),
    ("diameter_mm", r"(\d+(?:\.\d+)?)mm Diameter"),
    ("width_mm", r"(\d+(?:\.\d+)?)mm Width"),
    ("thickness_mm", r"(\d+(?:\.\d+)?)mm Thick(?:ness)?"),
    ("pitch", r"(\d+(?:\.\d+)?mm (?:HTD )?Pitch|MOD \d+(?:\.\d+)?)"),
    ("ratio", r"(\d+(?:\.\d+)?:1) Ratio"),
    ("rpm", r"(\d+(?:\.\d+)?) RPM"),
    ("durometer", r"(\d+A)\b"),
]
_DIM_RES = [(k, re.compile(p, re.I)) for k, p in _DIM_PATTERNS]
_NUMERIC_DIMS = {"holes", "teeth", "od_mm", "id_mm", "diameter_mm", "width_mm",
                 "thickness_mm", "rpm"}


def parse_dims(name: str, fields: dict[str, str]) -> dict:
    dims: dict = {}
    for key, rx in _DIM_RES:
        m = rx.search(name)
        if m:
            dims[key] = _num(m.group(1)) if key in _NUMERIC_DIMS else m.group(1)
    # Wheel diameter: "104mm Mecanum Wheel", "96mm GripForce Mecanum Wheel".
    m = re.search(r"(\d+(?:\.\d+)?)mm (?:Diameter )?[\w ]*?(?:Wheel|Tire)", name)
    if m and "diameter_mm" not in dims:
        dims["diameter_mm"] = _num(m.group(1))
    for key, value in fields.items():
        if key.startswith("filter_") and value:
            dims.setdefault(key.removeprefix("filter_").lower(), clean(value))
    return dims


def length_mm(name: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)?)mm (?:Pitch )?Length", name)
    return str(_num(m.group(1))) if m else ""


def mass_g(fields: dict[str, str]) -> str:
    raw = (fields.get("spec_Weight") or "").replace(",", "")
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(g|kg)\s*", raw, re.I)
    if not m:
        return ""
    v = float(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
    return str(_num(f"{v:.1f}"))


def series(name: str, sku: str) -> str:
    m = re.match(r"(\d{4}) Series", name)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(\d{4})-\d{4}-\d{4}", sku)
    return m.group(1) if m else ""


def hole_pattern(fields: dict[str, str]) -> str:
    for key in ("filter_pattern", "filter_Pattern", "spec_Pattern",
                "filter_hole pattern", "spec_Hole Pattern"):
        if fields.get(key):
            return clean(fields[key])
    return ""


def row_from_product(p: dict) -> dict | None:
    sku = clean(p.get("sku"))
    if not sku or sku.lower().startswith("rd-"):  # "see also" redirect entries
        return None
    name = clean(p.get("name"))
    cats = [clean(c) for c in p.get("category") or []]
    if any(c.startswith("MERCH") for c in cats):
        return None
    fields = {clean(f.get("name")): str(f.get("value") or "")
              for f in p.get("custom_fields") or []}
    ptype = classify(name, cats)
    step = fields.get("download_STEP File", "").strip()
    price = ((p.get("price") or {}).get("without_tax") or {}).get("value")
    dims, length = parse_dims(name, fields), length_mm(name)
    if ptype in ("motor", "servo"):
        # "24mm Length 8mm REX Shaft" describes the output shaft, not the part.
        if length:
            dims["shaft_length_mm"], length = _num(length), ""
        if "bore" in dims:
            dims["shaft"] = dims.pop("bore")
    return {
        "sku": sku,
        "name": name,
        "type": ptype,
        "series": series(name, sku),
        "length_mm": length,
        "dims": json.dumps(dims, ensure_ascii=False) if dims else "",
        "hole_pattern": hole_pattern(fields),
        "mass_g": mass_g(fields),
        "price": f"{price:.2f}" if isinstance(price, (int, float)) else "",
        "counts_as": counts_as(ptype),
        "product_url": p.get("url") or "",
        "step_url": (BASE + step if step.startswith("/") else step),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="use the cache only")
    args = ap.parse_args()
    products = crawl(args.offline)
    rows = [r for r in map(row_from_product, products.values()) if r]
    rows.sort(key=lambda r: r["sku"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} parts → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
