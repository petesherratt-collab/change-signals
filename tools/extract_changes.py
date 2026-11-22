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

import yaml
from kibitzr_archive.store import ArchiveStore

from build_config import check_name
from probe import selected_text

MAX_LINES = 60  # per side; a whole-page rewrite is summarised, not copied


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
            text = selected_text(store.get_blob(obs["content_sha256"]), page.get("css"))
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
    records = extract(watch, ArchiveStore(args.archive), done)
    with open(args.out, "a", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    state_path.write_text(json.dumps(done, indent=1))
    print(f"{len(records)} new changes")


if __name__ == "__main__":
    main()
