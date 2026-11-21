"""Label each new page change buy, sell or irrelevant, through the Adaptive Router.

    python tools/label_changes.py --changes data/changes.jsonl --labels data/labels.jsonl \\
        --router ../Adaptive_Router --store data/router_store

Each change is one request of a single fixed shape. The router races several
models for the first valid answer; when the models agree, the answer becomes an
example, and once enough agree it may promote code (for instance, code that
recognises a changed date or a reordered list as irrelevant). No model judges
code: promotion is by reproducing agreed answers.

Every label records how it was produced (code or model race, which model, how
long) and whether the racing models agreed. Disagreement is the uncertainty
flag: on earlier jobs agreed answers were right 94% of the time against 18%
for disagreed ones. Labels are append-only and written before any price after
the change is known; scoring is a separate step.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

SPEC = (
    "A UK-listed company's own web page changed between two daily checks. 'removed' lists text lines that "
    "disappeared and 'added' lists lines that appeared; 'page_kind' says which page it is (careers, board or "
    "news). Decide what the change suggests for the company's share price over the next few weeks, using "
    "only this change: return \"buy\" if it is a meaningful sign of improving business (for example many "
    "more vacancies, new senior hires, expansion, new contracts), \"sell\" if it is a meaningful sign of "
    "worsening business (for example vacancies cut or frozen, directors removed or departing unexpectedly, "
    "closures, profit warnings, delays), and \"irrelevant\" for anything else, including cosmetic or routine "
    "changes such as dates, cookie or menu text, reordering, a single routine vacancy, or news the market "
    "already had. Most changes are irrelevant. Return exactly one of \"buy\", \"sell\", \"irrelevant\"."
)
SIGNATURE = "def solve(company, page_kind, removed, added):"
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


def last_observation(log_path, request_id):
    """The racers' agreement for a request, from the router's log (None if not observed)."""
    try:
        lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines[-200:]):
        record = json.loads(line)
        if record.get("record_type") == "fast_path_observation" and record.get("request_id") == request_id:
            return {"agreed": record["agreed"], "distinct_valid_answers": record["distinct_valid_answers"],
                    "models": [m["model"] for m in record["models"] if m.get("valid")]}
    return None


def last_request_id(log_path):
    lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    for line in reversed(lines[-200:]):
        record = json.loads(line)
        if record.get("record_type") == "fast_path_request":
            return record["request_id"]
    return None


def make_router(router_dir, store, log_path):
    sys.path.insert(0, str(Path(router_dir).resolve()))
    import fast_path  # noqa: E402  (from the Adaptive Router checkout)
    root = Path(router_dir)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    settings = json.loads((root / "config_fast_path.json").read_text(encoding="utf-8"))
    return fast_path, fast_path.FastPathRouter({"remote": config["remote"], "fast_path": settings["fast_path"]},
                                               store_dir=store, log_path=log_path)


def label_all(changes, done, router, fast_path, log_path):
    out = []
    for change in changes:
        key = f"{change['check']}#{change['poll_id']}"
        if key in done:
            continue
        args = [change["company"], change["kind"], clip(change["removed"]), clip(change["added"])]
        result = router.handle(fast_path.FastPathRequest(SPEC, SIGNATURE, args, []))
        router.drain()
        value = result["value"]
        observed = last_observation(log_path, last_request_id(log_path)) if result["route"] == "model" else None
        out.append({"key": key, "check": change["check"], "company": change["company"], "kind": change["kind"],
                    "polled_at": change["polled_at"],
                    "label": value if value in LABELS else None, "raw_value": None if value in LABELS else value,
                    "route": result["route"], "model": result["model"], "ms": round(result["total_ms"]),
                    "agreed": observed["agreed"] if observed else None,
                    "distinct_answers": observed["distinct_valid_answers"] if observed else None})
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
    routes = {}
    for r in records:
        routes[r["route"]] = routes.get(r["route"], 0) + 1
    print(f"{len(records)} labelled; routes {routes}")


if __name__ == "__main__":
    main()
