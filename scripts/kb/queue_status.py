"""Set the status/note of rows in kb/ingest/queue.csv.

Usage: python3 -I scripts/kb/queue_status.py <status> "<note>" <id>...
       python3 -I scripts/kb/queue_status.py next <n>     print the next n queued ids
"""

import csv
import sys
from pathlib import Path

QUEUE = Path(__file__).resolve().parents[2] / "kb/ingest/queue.csv"


def main():
    with QUEUE.open() as f:
        rows = list(csv.DictReader(f))
    if sys.argv[1] == "next":
        print(
            "\n".join(
                [r["id"] for r in rows if r["status"] == "queued"][: int(sys.argv[2])]
            )
        )
        return
    status, note, ids = sys.argv[1], sys.argv[2], set(sys.argv[3:])
    for r in rows:
        if r["id"] in ids:
            r["status"], r["note"] = status, note
            ids.discard(r["id"])
    if ids:
        raise SystemExit(f"not in queue: {sorted(ids)}")
    with QUEUE.open("w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys())
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
