"""Fetch one queued robot from Onshape into kb/ingest/drafts/<id>/ (brief step 1).

Usage: python3 -I scripts/kb/onshape_fetch.py <command>
  fetch <id>             doc info, tree, BOM, robot render; prints a tree summary
  render <id> <path>...  render subassemblies; path = instance names joined by " / "
  tree <id> [depth]      tree summary again (no API call)
  parts <id> <path>...   recursive part names under each path (no API call)
  step <id> [transl_id]  export the assembly as STEP for Fusion renders (3-5 calls);
                         pass a translation id to resume one already started
  calls                  calls logged so far

Every Onshape call is appended to kb/ingest/api_calls.csv. Calls stop once the run
budget (env ONSHAPE_BUDGET, default 150, counted from env ONSHAPE_RUN_START, ISO UTC) is
used up, or the yearly log reaches 2,000 (warns past 1,500). Only 2xx/3xx are logged.
"""

import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API = "https://cad.onshape.com/api/v10"
REPO = Path(__file__).resolve().parents[2]
INGEST = REPO / "kb/ingest"
LOG = INGEST / "api_calls.csv"
RUN_START = os.environ.get(
    "ONSHAPE_RUN_START", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
)
YEAR_STOP, YEAR_WARN = 2000, 1500
BUDGET = int(os.environ.get("ONSHAPE_BUDGET", "150"))
HARDWARE = re.compile(
    r"\b(screw|nut|locknut|bolt|washer|insert|rivet|shcs|bhcs|fhcs|socket m\d"
    r"|set ?screw|zip ?tie|m\d+x\d+)\b",
    re.I,
)


class BudgetError(RuntimeError):
    pass


def _auth():
    env = {}
    for line in (
        (Path.home() / ".config/fusion-mcp/onshape.env").read_text().splitlines()
    ):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip().removeprefix("export ").strip()] = v.strip().strip("\"'")
    token = f"{env['ONSHAPE_ACCESS_KEY']}:{env['ONSHAPE_SECRET_KEY']}"
    return "Basic " + base64.b64encode(token.encode()).decode()


AUTH = None


def _rows():
    if not LOG.exists():
        return []
    with LOG.open() as f:
        return list(csv.DictReader(f))


def _n(r):
    """A log row counts 1, except a summary row like '16-calls-before-log'."""
    m = re.match(r"(\d+)-calls", r["status"])
    return int(m.group(1)) if m else 1


def calls_used():
    """Calls logged since RUN_START (this run)."""
    return sum(_n(r) for r in _rows() if r["timestamp"] >= RUN_START)


def calls_year():
    year = datetime.now(timezone.utc).strftime("%Y")
    return sum(_n(r) for r in _rows() if r["timestamp"].startswith(year))


def _log(robot, path, status):
    """Only 2xx/3xx count against Onshape's yearly cap, so only those are logged."""
    if not 200 <= status < 400:
        return
    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "robot_id", "endpoint", "status"])
        w.writerow(
            [
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                robot,
                path,
                status,
            ]
        )


def get(robot, path, accept="application/json", data=None, raw=False):
    """GET (or POST when `data` is given) with one retry on 429/5xx.

    Returns parsed JSON, or bytes when `raw`.
    """
    global AUTH
    AUTH = AUTH or _auth()
    for attempt in (0, 1):
        if calls_used() >= BUDGET:
            raise BudgetError(f"run budget of {BUDGET} calls used up")
        if calls_year() >= YEAR_STOP:
            raise BudgetError(f"yearly hard stop of {YEAR_STOP} logged calls reached")
        headers = {"Authorization": AUTH, "Accept": accept}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        req = urllib.request.Request(API + path, body, headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            _log(robot, path.split("?")[0], 200)
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            _log(robot, path.split("?")[0], e.code)
            if (e.code == 429 or e.code >= 500) and attempt == 0:
                time.sleep(int(e.headers.get("Retry-After") or 10))
                continue
            raise


def queue_row(rid):
    with (INGEST / "queue.csv").open() as f:
        for r in csv.DictReader(f):
            if r["id"] == rid:
                return r
    raise SystemExit(f"{rid} not in queue.csv")


def ids_from_url(url):
    m = re.search(
        r"/documents/([0-9a-f]{24})/(w|v|m)/([0-9a-f]{24})/e/([0-9a-f]{24})", url
    )
    return (
        m.groups()
        if m
        else (re.search(r"/documents/([0-9a-f]{24})", url).group(1), None, None, None)
    )


def save(d, name, obj):
    (d / name).write_text(
        json.dumps(obj, indent=1) if not isinstance(obj, bytes) else obj.decode()
    )


def save_png(d, name, view):
    imgs = view.get("images") or []
    if imgs:
        (d / name).write_bytes(base64.b64decode(imgs[0]))
        return True
    return False


# ---- tree helpers ---------------------------------------------------------


def sub_key(i):
    return (
        i.get("documentId"),
        i.get("elementId"),
        i.get("configuration", ""),
        i.get("documentMicroversion"),
    )


def index_tree(asm):
    subs = {}
    for s in asm.get("subAssemblies", []):
        subs[
            (
                s["documentId"],
                s["elementId"],
                s.get("configuration", ""),
                s["documentMicroversion"],
            )
        ] = s
    return subs


def walk(asm, subs):
    """Yield (path, instance, depth) for every instance in the tree."""

    def rec(instances, prefix, depth):
        for inst in instances:
            p = f"{prefix} / {inst['name']}" if prefix else inst["name"]
            yield p, inst, depth
            if inst.get("type") == "Assembly":
                s = subs.get(sub_key(inst))
                if s:
                    yield from rec(s["instances"], p, depth + 1)

    yield from rec(asm["rootAssembly"]["instances"], "", 1)


def strip_count(name):
    return re.sub(r"\s*<\d+>$", "", name)


def parts_under(asm, subs, path):
    """Counter of part names under one assembly instance path (hardware removed)."""
    c = Counter()
    for p, inst, _ in walk(asm, subs):
        if (
            (p == path or p.startswith(path + " / ") or (path == "" and " / " not in p))
            and inst.get("type") == "Part"
            and not inst.get("suppressed")
        ):
            n = strip_count(inst["name"])
            if not HARDWARE.search(n):
                c[n] += 1
    return c


def summary(asm, subs, maxdepth=4):
    """Assembly instances as an indented tree.

    Same-name siblings collapse to ×N; small linked COTS assemblies are hidden.
    """
    root_doc = asm["rootAssembly"]["documentId"]
    rows, seen = [], {}
    for p, inst, depth in walk(asm, subs):
        if inst.get("type") != "Assembly" or depth > maxdepth or inst.get("suppressed"):
            continue
        n = sum(parts_under(asm, subs, p).values())
        linked = inst["documentId"] != root_doc
        if linked and n < 8:
            continue
        parent = p.rsplit(" / ", 1)[0] if " / " in p else ""
        key = (parent, strip_count(inst["name"]))
        if key in seen:
            seen[key][3] += 1
            continue
        row = [depth, strip_count(inst["name"]), n, 1, linked, p]
        seen[key] = row
        rows.append(row)
    hidden = {r[5] for r in rows}
    lines = []
    for depth, name, n, k, linked, p in rows:
        if (
            any(p.startswith(h + " / ") for h in hidden if h != p)
            and depth > 1
            and p.rsplit(" / ", 1)[0] not in hidden
        ):
            continue
        lines.append(
            f"{'  ' * (depth - 1)}{name}{f' ×{k}' if k > 1 else ''}  "
            f"[{n} parts{', linked' if linked else ''}]  path={p}"
        )
    loose = Counter(
        strip_count(i["name"])
        for i in asm["rootAssembly"]["instances"]
        if i.get("type") == "Part" and not HARDWARE.search(i["name"])
    )
    lines.append(
        f"(root loose parts: {sum(loose.values())}) "
        + ", ".join(f"{q}× {n}" if q > 1 else n for n, q in loose.most_common(40))
    )
    return lines


# ---- commands --------------------------------------------------------------


def cmd_fetch(rid):
    row = queue_row(rid)
    d = INGEST / "drafts" / rid
    d.mkdir(parents=True, exist_ok=True)
    did, wvm, wid, eid = ids_from_url(row["url"])
    if (d / "assembly.json").exists() and (d / "ids.json").exists():
        ids = json.loads((d / "ids.json").read_text())
        did, wvm, wid, eid = ids["did"], ids["wvm"], ids["wid"], ids["eid"]
        asm = json.loads((d / "assembly.json").read_text())
        doc = (
            json.loads((d / "document.json").read_text())
            if (d / "document.json").exists()
            else {}
        )
        return _finish(rid, d, did, wvm, wid, eid, asm, doc)
    # GET /documents only when the team is unknown (the owner can hint at it)
    # or the URL has no workspace.
    doc = {}
    if not (row.get("team_number") or team_in(row["title"])) or not wid:
        doc = get(rid, f"/documents/{did}")
        save(
            d,
            "document.json",
            {
                k: doc.get(k)
                for k in (
                    "name",
                    "owner",
                    "public",
                    "description",
                    "defaultWorkspace",
                    "createdAt",
                    "modifiedAt",
                )
            },
        )
    if not wid:
        wvm, wid = "w", doc["defaultWorkspace"]["id"]
    asm = None
    if eid:
        try:
            asm = get(rid, f"/assemblies/d/{did}/{wvm}/{wid}/e/{eid}")
        except urllib.error.HTTPError as e:
            if e.code not in (400, 404):
                raise
    if asm is None or "rootAssembly" not in asm:
        els = get(rid, f"/documents/d/{did}/{wvm}/{wid}/elements")
        asms = [e for e in els if e.get("elementType") == "ASSEMBLY"]
        save(
            d,
            "elements.json",
            [{"id": e["id"], "name": e["name"], "type": e["elementType"]} for e in els],
        )
        if not asms:
            raise SystemExit("no assembly element in document")
        pick = next(
            (
                a
                for a in asms
                if any(
                    w in a["name"].lower()
                    for w in ("robot", "full", "main", "master", "final")
                )
            ),
            asms[0],
        )
        print(
            f"element {eid} is not an assembly; using '{pick['name']}' "
            f"of {[a['name'] for a in asms]}"
        )
        eid = pick["id"]
        asm = get(rid, f"/assemblies/d/{did}/{wvm}/{wid}/e/{eid}")
    save(d, "assembly.json", asm)
    save(d, "ids.json", {"did": did, "wvm": wvm, "wid": wid, "eid": eid})
    return _finish(rid, d, did, wvm, wid, eid, asm, doc)


def team_in(text):
    """A 3-5 digit team number in a title, ignoring season years like 2025 or 2026."""
    for m in re.finditer(r"(?<![\d.])(\d{3,5})(?![\d.])", text or ""):
        if not 2015 <= int(m.group(1)) <= 2030:
            return m.group(1)
    return None


def _finish(rid, d, did, wvm, wid, eid, asm, doc):
    def bom():
        return get(
            rid,
            f"/assemblies/d/{did}/{wvm}/{wid}/e/{eid}/bom?indented=false&multiLevel=true",
        )

    def render():
        return get(
            rid,
            f"/assemblies/d/{did}/{wvm}/{wid}/e/{eid}/shadedviews?viewMatrix=isometric&outputWidth=800&outputHeight=600&pixelSize=0",
        )

    if (d / "bom.json").exists():
        b, ok = json.loads((d / "bom.json").read_text()), (d / "robot.png").exists()
    else:
        with ThreadPoolExecutor(2) as ex:
            fb, fr = ex.submit(bom), ex.submit(render)
            b = fb.result()
            try:
                ok = save_png(d, "robot.png", fr.result())
            except urllib.error.HTTPError as e:
                ok = False
                print(f"robot render failed: HTTP {e.code}")
        save(d, "bom.json", b)
    print(
        f"# {rid}  doc '{doc.get('name')}'  owner {doc.get('owner', {}).get('name')}  "
        f"public={doc.get('public')}  render={'ok' if ok else 'none'}"
    )
    print(f"# description: {(doc.get('description') or '')[:200]}")
    subs = index_tree(asm)
    print("\n".join(summary(asm, subs)))
    print("# BOM (no hardware):")
    print(bom_lines(b))


def bom_lines(b):
    heads = {h["id"]: h["name"] for h in b.get("headers", [])}
    out = Counter()
    for r in b.get("rows", []):
        v = {heads.get(k, k): val for k, val in r.get("headerIdToValue", {}).items()}
        name = v.get("Name") or ""
        if isinstance(name, dict):
            name = name.get("name", "")
        if HARDWARE.search(name):
            continue
        q = v.get("Quantity") or 1
        try:
            q = int(float(q))
        except (TypeError, ValueError):
            q = 1
        out[name] += q
    return "\n".join(
        f"  {q}× {n}" for n, q in sorted(out.items(), key=lambda x: (-x[1], x[0]))
    )


def cmd_render(rid, paths):
    d = INGEST / "drafts" / rid
    asm = json.loads((d / "assembly.json").read_text())
    subs = index_tree(asm)
    by_path = {p: inst for p, inst, _ in walk(asm, subs)}
    results = {}

    def one(path):
        inst = by_path.get(path)
        if not inst or inst.get("type") != "Assembly":
            return path, "not an assembly path"
        q = "viewMatrix=isometric&outputWidth=600&outputHeight=450&pixelSize=0"
        if inst.get("configuration") and inst["configuration"] != "default":
            q += "&configuration=" + urllib.parse.quote(inst["configuration"])
        try:
            v = get(
                rid,
                f"/assemblies/d/{inst['documentId']}/m/{inst['documentMicroversion']}/e/{inst['elementId']}/shadedviews?{q}",
            )
        except urllib.error.HTTPError as e:
            return path, f"HTTP {e.code}"
        fname = (
            "mech-" + re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")[-60:] + ".png"
        )
        return path, fname if save_png(d, fname, v) else "no image"

    with ThreadPoolExecutor(4) as ex:
        for path, res in ex.map(one, paths):
            results[path] = res
            print(f"{path}: {res}")
    old = (
        json.loads((d / "renders.json").read_text())
        if (d / "renders.json").exists()
        else {}
    )
    old.update(results)
    save(d, "renders.json", old)


def cmd_step(rid, translation_id=None):
    """Export the assembly as STEP to drafts/<id>/robot.step (about 3-5 calls)."""
    d = INGEST / "drafts" / rid
    ids = json.loads((d / "ids.json").read_text())
    did, wvm, wid, eid = ids["did"], ids["wvm"], ids["wid"], ids["eid"]
    if translation_id:
        t = get(rid, f"/translations/{translation_id}")
    else:
        t = get(
            rid,
            f"/assemblies/d/{did}/{wvm}/{wid}/e/{eid}/translations",
            data={
                "formatName": "STEP",
                "storeInDocument": False,
                "flattenAssemblies": False,
            },
        )
        print(f"translation {t['id']}", flush=True)
    # Each poll is a logged call, so poll slowly: big robots take several minutes.
    for _ in range(20):
        if t.get("requestState") != "ACTIVE":
            break
        time.sleep(60)
        t = get(rid, f"/translations/{t['id']}")
    if t.get("requestState") != "DONE":
        raise SystemExit(
            f"translation {t.get('requestState')}: {t.get('failureReason')}"
        )
    ext = t["resultExternalDataIds"][0]
    out = d / "robot.step"
    out.write_bytes(
        get(
            rid,
            f"/documents/d/{did}/externaldata/{ext}",
            "application/octet-stream",
            raw=True,
        )
    )
    print(f"{out}  {out.stat().st_size // 1024} KB")


def cmd_parts(rid, paths):
    d = INGEST / "drafts" / rid
    asm = json.loads((d / "assembly.json").read_text())
    subs = index_tree(asm)
    for p in paths:
        c = parts_under(asm, subs, p)
        print(f"## {p}  ({sum(c.values())} parts)")
        for n, q in sorted(c.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {q}× {n}")


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    try:
        if cmd == "fetch":
            cmd_fetch(args[0])
        elif cmd == "render":
            cmd_render(args[0], args[1:])
        elif cmd == "tree":
            d = INGEST / "drafts" / args[0]
            asm = json.loads((d / "assembly.json").read_text())
            print(
                "\n".join(
                    summary(asm, index_tree(asm), int(args[1]) if len(args) > 1 else 4)
                )
            )
        elif cmd == "step":
            cmd_step(*args[:2])
        elif cmd == "parts":
            cmd_parts(args[0], args[1:])
        elif cmd == "calls":
            print(
                f"run since {RUN_START}: {calls_used()} / {BUDGET}; "
                f"year: {calls_year()} / {YEAR_STOP}"
            )
    except BudgetError as e:
        raise SystemExit(f"STOP: {e}")
    finally:
        if cmd in ("fetch", "render", "step"):
            y = calls_year()
            print(
                f"# calls this run: {calls_used()} / {BUDGET}; year {y} / {YEAR_STOP}"
                + ("  WARNING: past 1,500" if y > YEAR_WARN else "")
            )


if __name__ == "__main__":
    main()
