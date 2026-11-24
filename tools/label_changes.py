"""Label each new page change, in two steps, through the Adaptive Router.

    python tools/label_changes.py --changes data/changes.jsonl --labels data/labels.jsonl \\
        --router router --store data/router_store

Step A, "is this change cosmetic?": a repeated, rule-like question (a date moved,
items reordered, one routine vacancy swapped for another). It goes through the
router's fast path with learning on: racing models answer, agreed answers become
examples, and code may be promoted once it reproduces them. Measuring how much of
step A becomes code is the router experiment (AMENDMENT_1.md).

Step B, "buy, sell or irrelevant?", for changes that are not cosmetic: a judgement,
raced across every model and never turned into code. The first valid answer is the
label (time first, as everywhere in the router); every model's answer is kept, and
disagreement is the uncertainty flag.

Labels are append-only and written in the same run as the poll that found the
change, before any later price exists. Scoring is tools/score.py.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, wait
import json
import os
from pathlib import Path
import sys
import time

SPEC_COSMETIC = (
    "A UK-listed company's own web page changed between two daily checks. 'removed' lists text lines that "
    "disappeared and 'added' lists lines that appeared; 'page_kind' is careers, board or news. Return true if "
    "the change is cosmetic or routine and says nothing about how the business is doing: only dates or times "
    "changed; the same items reordered; wording, menus, cookie or footer text; one routine vacancy replaced by "
    "another; a routine shareholding notice. Return false if it could matter: vacancies added or removed in "
    "numbers, a director or senior manager arriving or leaving, a new announcement about trading, results, "
    "contracts, sites, planning, closures, financing or acquisitions. Return exactly true or false."
)
SIGNATURE_COSMETIC = "def solve(page_kind, removed, added):"

SPEC_LABEL = (
    "A UK-listed company's own web page changed between two daily checks, and the change is not merely "
    "cosmetic. 'removed' lists text lines that disappeared and 'added' lists lines that appeared; 'page_kind' "
    "says which page it is (careers, board or news). Using only this change, decide what it suggests for the "
    "company's share price over the next few weeks: \"buy\" for a meaningful sign of improving business (many "
    "more vacancies, senior hires, expansion, new contracts or approvals), \"sell\" for a meaningful sign of "
    "worsening business (vacancies cut or frozen, unexpected departures, closures, profit warnings, delays), "
    "and \"irrelevant\" otherwise. Return exactly one of \"buy\", \"sell\", \"irrelevant\"."
)
SIGNATURE_LABEL = "def solve(company, page_kind, removed, added):"
LABELS = {"buy", "sell", "irrelevant"}
MAX_CHARS = 6000  # per side, so one huge rewrite cannot blow the prompt


def clip(lines):
    out, used = [], 0
    for line in lines:
        if used + len(line) > MAX_CHARS:
            out.append("[... more lines not shown]")
            break
        out.append(line)
        used += len(line)
    return out


def last_record(log_path, record_type, request_id=None):
    try:
        lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines[-300:]):
        record = json.loads(line)
        if record.get("record_type") == record_type and (request_id is None or record.get("request_id") == request_id):
            return record
    return None


def make_router(router_dir, store, log_path):
    sys.path.insert(0, str(Path(router_dir).resolve()))
    import fast_path  # noqa: E402  (from the Adaptive Router checkout)
    root = Path(router_dir)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    settings = json.loads((root / "config_fast_path.json").read_text(encoding="utf-8"))
    return fast_path, fast_path.FastPathRouter({"remote": config["remote"], "fast_path": settings["fast_path"]},
                                               store_dir=store, log_path=log_path)


def step_a(router, fast_path, log_path, change):
    """Cosmetic or not, through the fast path with learning on."""
    args = [change["kind"], clip(change["removed"]), clip(change["added"])]
    result = router.handle(fast_path.FastPathRequest(SPEC_COSMETIC, SIGNATURE_COSMETIC, args, []))
    router.drain()
    agreed = None
    if result["route"] == "model":
        request = last_record(log_path, "fast_path_request")
        observed = last_record(log_path, "fast_path_observation", request and request["request_id"])
        agreed = observed["agreed"] if observed else None
    value = result["value"]
    return {"cosmetic": value if isinstance(value, bool) else None, "a_route": result["route"],
            "a_model": result["model"], "a_ms": round(result["total_ms"]), "a_agreed": agreed}


def step_b(router, fast_path, change):
    """Buy/sell/irrelevant: raced, first valid answer wins, every answer kept; never learned."""
    args = [change["company"], change["kind"], clip(change["removed"]), clip(change["added"])]
    prompt = fast_path.build_answer_prompt(SPEC_LABEL, SIGNATURE_LABEL, args)
    started = time.perf_counter()
    futures = router.start_prompt_race(prompt)
    winner, first_ms, remaining = None, None, set(futures)
    while remaining and winner is None:
        done, remaining = wait(remaining, return_when=FIRST_COMPLETED)
        valid = [f.result() for f in done if f.result()["valid"] and f.result()["value"] in LABELS]
        if valid:
            winner = min(valid, key=lambda r: r["total_ms"] or 0)
            first_ms = (time.perf_counter() - started) * 1000
    answers = [f.result() for f in futures]  # waits for the rest, for the agreement record only
    votes = Counter(a["value"] for a in answers if a["valid"] and a["value"] in LABELS)
    return {"label": winner["value"] if winner else None, "b_model": winner["model"] if winner else None,
            "b_ms": round(first_ms) if first_ms else None, "b_votes": dict(votes),
            "b_agreed": len(votes) == 1 and sum(votes.values()) >= 2}


def label_all(changes, done, router, fast_path, log_path):
    out = []
    for change in changes:
        key = f"{change['check']}#{change['poll_id']}"
        if key in done:
            continue
        record = {"key": key, "check": change["check"], "company": change["company"], "kind": change["kind"],
                  "polled_at": change["polled_at"]}
        a = step_a(router, fast_path, log_path, change)
        record.update(a)
        if a["cosmetic"] is True:
            record.update({"label": "irrelevant", "b_model": None, "b_ms": None, "b_votes": {}, "b_agreed": None})
        else:  # not cosmetic, or step A gave no usable answer: ask the judgement question
            record.update(step_b(router, fast_path, change))
        # fields tools/score.py reads (unchanged since the plan was frozen)
        record["route"] = a["a_route"] if a["cosmetic"] is True else "model"
        record["agreed"] = a["a_agreed"] if a["cosmetic"] is True else record["b_agreed"]
        record["ms"] = a["a_ms"] + (record["b_ms"] or 0)
        out.append(record)
        done.add(key)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--changes", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--router", required=True, help="path to an Adaptive_Router checkout")
    parser.add_argument("--store", required=True)
    parser.add_argument("--max", type=int, default=200, help="most changes to label in one run")
    args = parser.parse_args()
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set: nothing labelled")
        return
    changes = [json.loads(l) for l in Path(args.changes).read_text(encoding="utf-8").splitlines() if l.strip()] \
        if Path(args.changes).exists() else []
    labels_path = Path(args.labels)
    done = {json.loads(l)["key"] for l in labels_path.read_text(encoding="utf-8").splitlines() if l.strip()} \
        if labels_path.exists() else set()
    log_path = str(Path(args.store) / "router_runs.jsonl")
    Path(args.store).mkdir(parents=True, exist_ok=True)
    fast_path, router = make_router(args.router, args.store, log_path)
    todo = [c for c in changes if f"{c['check']}#{c['poll_id']}" not in done][:args.max]
    try:
        records = label_all(todo, done, router, fast_path, log_path)
    finally:
        router.close()
    with open(labels_path, "a", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(records)} labelled: {dict(Counter(r['label'] for r in records))}; "
          f"step A routes {dict(Counter(r['a_route'] for r in records))}")


if __name__ == "__main__":
    main()
