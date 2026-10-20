"""Rate a team-season from FTC Scout.

Formula: docs/plans/knowledge-base.md, "Rating".

Usage: python3 -I scripts/kb/ftcscout.py <team> <season year> [<team> <year> ...]
Prints one JSON rating object per pair, ready for the draft's `rating` field.
"""

import json
import sys
import urllib.request
from datetime import date

URL = "https://api.ftcscout.org/graphql"
QUERY = """query($n: Int!, $s: Int!) { teamByNumber(number: $n) { name
  quickStats(season: $s) { tot { value rank } count }
  events(season: $s) { event { name type } } } }"""
TOP = {"FIRSTChampionship"}
MID = {"Championship", "Premier", "SuperQualifier"}
ORDER = [
    "FIRSTChampionship",
    "Championship",
    "Premier",
    "SuperQualifier",
    "Qualifier",
    "LeagueTournament",
    "LeagueMeet",
]


def rate(team, season):
    body = json.dumps({"query": QUERY, "variables": {"n": team, "s": season}}).encode()
    req = urllib.request.Request(
        URL, body, {"Content-Type": "application/json", "User-Agent": "fusion-mcp-kb"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        t = (json.load(r).get("data") or {}).get("teamByNumber")
    if not t:
        return {
            "basis": "unknown",
            "multiplier": 1.0,
            "detail": f"Team {team} not found on FTC Scout.",
        }
    qs, events = t.get("quickStats"), [e["event"] for e in t.get("events") or []]
    if not qs or not qs.get("count"):
        return {
            "basis": "unknown",
            "multiplier": 1.0,
            "team_name": t["name"],
            "detail": f"No {season} stats on FTC Scout yet ({len(events)} events).",
        }
    rank, count = qs["tot"]["rank"], qs["count"]
    opr_pct = 1 - rank / count
    types = {e["type"] for e in events}
    adv = 1.0 if types & TOP else 0.5 if types & MID else 0.0
    score = 0.7 * opr_pct + 0.3 * adv
    best = (
        min(events, key=lambda e: ORDER.index(e["type"]) if e["type"] in ORDER else 99)
        if events
        else None
    )
    return {
        "basis": "ftcscout",
        "multiplier": round(0.8 + 0.5 * score, 3),
        "opr_pct": round(opr_pct, 3),
        "opr_rank": rank,
        "teams": count,
        "best_event": best["type"] if best else None,
        "fetched": date.today().isoformat(),
        "team_name": t["name"],
        "detail": f"OPR {round(opr_pct * 100)}th pct of {count}"
        + (f" · {best['name']}" if best else ""),
    }


def main():
    a = sys.argv[1:]
    for team, season in zip(a[::2], a[1::2]):
        print(team, season, json.dumps(rate(int(team), int(season))))


if __name__ == "__main__":
    main()
