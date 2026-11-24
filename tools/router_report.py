"""The router measures fixed in AMENDMENT_1.md, by ISO week, from data/labels.jsonl.

    python tools/router_report.py --labels data/labels.jsonl --out data/router_report.md

Descriptive from week 1. For each week:
- step A (cosmetic?): changes asked; share answered by promoted code; share where racing models agreed;
- step B (buy/sell/irrelevant): changes asked; share where the models agreed (unflagged);
- labels: buy / sell / irrelevant;
- time: median milliseconds per change, both steps together.
Cost is read from OpenRouter's usage for the key, not computed here.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
from pathlib import Path
import statistics


def week(ts):
    y, w, _ = dt.date.fromisoformat(ts[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def pct(a, b):
    return f"{a / b:.0%}" if b else "-"


def report(labels):
    by = collections.defaultdict(list)
    for r in labels:
        by[week(r["polled_at"])].append(r)
    lines = ["# Router report", "",
             "| week | changes | A: by code | A: models agreed | B: asked | B: models agreed | buy / sell / irrelevant | median ms |",
             "|---|---|---|---|---|---|---|---|"]
    for wk in sorted(by):
        rs = by[wk]
        a_code = sum(r.get("a_route") == "code" for r in rs)
        a_obs = [r["a_agreed"] for r in rs if r.get("a_agreed") is not None]
        b = [r for r in rs if r.get("b_model") or r.get("b_votes")]
        b_ok = sum(bool(r.get("b_agreed")) for r in b)
        c = collections.Counter(r.get("label") for r in rs)
        ms = statistics.median([r["ms"] for r in rs if r.get("ms") is not None] or [0])
        lines.append(f"| {wk} | {len(rs)} | {pct(a_code, len(rs))} | {pct(sum(a_obs), len(a_obs))} | {len(b)} | "
                     f"{pct(b_ok, len(b))} | {c['buy']} / {c['sell']} / {c['irrelevant']} | {ms:.0f} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    path = Path(args.labels)
    labels = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
    text = report(labels)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
