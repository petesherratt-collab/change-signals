"""Turn the archive into a list of document changes, one line per change.

    python tools/extract_changes.py --archive data/archive --out data/changes.jsonl

For each check, reads the retained raw responses in poll order, re-derives the
selected text with the page's own selector (so nothing depends on trusting a
stored extraction), and writes a record whenever that text differs from the
previous observation: which lines were removed and which added. Lines that
differ only in dates, times or numbers-of-items counters are still reported;
deciding what is noise is the labelling step's job, and the evidence of what
it decided stays in the record.

Already-extracted polls are skipped, so the step can run after every poll.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import yaml
from kibitzr_archive.store import ArchiveStore

from build_config import check_name
from probe import selected_text

MAX_LINES = 60  # per side; a whole-page rewrite is summarised, not copied

# Amendment 1 (24 Nov 2026, before any label): share-price widgets embedded in some pages
# change with the market, not the business. A label that saw them would be judging the very
# price move it is scored against, so they are removed before any change is recorded.
FILTER_VERSION = 2
PRICE_LINES = [
    re.compile(r"^[▲▼△▽]"),                                  # "▲ +6.0p · +2.07%"
    re.compile(r"^[+\-−]?\d[\d,]*\.\d+\s*p?$"),              # "296.0p", "33.60", "-0.30"
    re.compile(r"^[+\-−]?\d[\d,]*\s*p$"),                   # "296p"
    re.compile(r"^[+\-−]?\d[\d,]*(\.\d+)?\s*%$"),            # "+2.07%"
    re.compile(r"^share price\b", re.I),                   # "Share price at 23 Nov 26 16:35"
]


def strip_prices(text):
    """The page text without share-price lines. Whole numbers (e.g. a vacancy count) are kept."""
    return "\n".join(l for l in text.splitlines() if not any(p.search(l.strip()) for p in PRICE_LINES))


def observations(store, name):
    """Successful polls with a retained response, oldest first."""
    return [o for o in store.observations(name) if o["ok"]]


def diff(before, after):
    old, new = before.splitlines(), after.splitlines()
    removed = [l for l in old if l not in set(new)]
    added = [l for l in new if l not in set(old)]
    return removed, added


def extract(watch, store, done):
    """Records for polls after ``done[check]`` (the last poll id already handled)."""
    out = []
    for page in watch.get("pages") or []:
        if not str(page.get("status", "")).startswith("passed"):
            continue
        name = check_name(page)
        previous_text, last = None, done.get(name, 0)
        for obs in observations(store, name):
            # get_blob checks the bytes still hash to the digest the poll chain committed to
            text = strip_prices(selected_text(store.get_blob(obs["content_sha256"]), page.get("css")))
            if obs["id"] > last and previous_text is not None and text != previous_text:
                removed, added = diff(previous_text, text)
                if removed or added:
                    out.append({"check": name, "company": page["company"], "kind": page["kind"],
                                "poll_id": obs["id"], "polled_at": obs["polled_at"],
                                "removed": removed[:MAX_LINES], "added": added[:MAX_LINES],
                                "removed_total": len(removed), "added_total": len(added)})
            previous_text = text
            done[name] = max(done.get(name, 0), obs["id"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with open("watchlist.yml", encoding="utf-8") as handle:
        watch = yaml.safe_load(handle)
    state_path = Path(args.out).with_suffix(".state.json")
    done = json.loads(state_path.read_text()) if state_path.exists() else {}
    if done.get("_filter_version") != FILTER_VERSION:
        # changes are derived data: rebuild them from the archive under the current filter
        # (the archive itself is never touched). Refused once anything has been labelled.
        labels = Path(args.out).with_name("labels.jsonl")
        if labels.exists() and labels.read_text().strip():
            raise SystemExit("filter changed after labelling began; record an amendment and rebuild deliberately")
        done = {}
        Path(args.out).write_text("")
    done["_filter_version"] = FILTER_VERSION
    records = extract(watch, ArchiveStore(args.archive), done)
    with open(args.out, "a", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    state_path.write_text(json.dumps(done, indent=1))
    print(f"{len(records)} new changes")


if __name__ == "__main__":
    main()
