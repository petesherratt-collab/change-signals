"""Score buy and sell labels against what the share price did next (PLAN.md, frozen rules).

    python tools/score.py --labels data/labels.jsonl --out data/score.md [--prices data/prices]

For each buy or sell label: entry is the first trading-day close strictly
after the UTC date of the poll that saw the change (so no price the labeller
could have seen is used). The excess return over 5 and 20 trading days is the
stock's return minus the benchmark's over the same closes. Several labels for
one company from one poll date are netted into one event (buy +1, sell -1;
a net of zero drops the event), so a page rewrite cannot count many times.

Primary statistic: mean 20-day excess of buy events minus mean of sell events,
with a one-sided permutation test (labels shuffled among scored events, 10,000
times, fixed seed). Before the decision point in PLAN.md the result is
descriptive only.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
from pathlib import Path
import random
import statistics

import requests
import yaml

HORIZONS = (5, 20)
PRIMARY = 20
PERMUTATIONS = 10_000
SEED = 20261121
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"


def closes(symbol, cache_dir=None):
    """[(date, close)] oldest first, from Yahoo's chart API; cached per day if cache_dir is given."""
    today = datetime.date.today().isoformat()
    cache = Path(cache_dir, f"{symbol}_{today}.json") if cache_dir else None
    if cache and cache.exists():
        return [(datetime.date.fromisoformat(d), c) for d, c in json.loads(cache.read_text())]
    r = requests.get(YAHOO.format(symbol=symbol), headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    stamps = result["timestamp"]
    prices = result["indicators"]["quote"][0]["close"]
    series = [(datetime.datetime.utcfromtimestamp(t).date(), c) for t, c in zip(stamps, prices) if c is not None]
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([(d.isoformat(), c) for d, c in series]))
    return series


def events(labels, tickers):
    """Net buy/sell labels per (company, poll date) into signed events."""
    net = collections.defaultdict(int)
    for r in labels:
        if r.get("label") in ("buy", "sell") and r["company"] in tickers:
            day = r["polled_at"][:10]
            net[(r["company"], day)] += 1 if r["label"] == "buy" else -1
    return [{"company": c, "date": datetime.date.fromisoformat(d), "side": "buy" if n > 0 else "sell"}
            for (c, d), n in sorted(net.items()) if n != 0]


def excess(series, bench, when, horizon):
    """Stock minus benchmark return from the first close after ``when`` over ``horizon`` closes, or None."""
    after = [i for i, (d, _) in enumerate(series) if d > when]
    if not after or after[0] + horizon >= len(series):
        return None
    i = after[0]
    start_day, end_day = series[i][0], series[i + horizon][0]
    b = dict(bench)
    if start_day not in b or end_day not in b:
        return None
    return (series[i + horizon][1] / series[i][1] - 1) - (b[end_day] / b[start_day] - 1)


def permutation_p(buys, sells, seed=SEED, n=PERMUTATIONS):
    """One-sided: chance that shuffled labels give a buy-minus-sell gap at least as large."""
    observed = statistics.mean(buys) - statistics.mean(sells)
    pooled, k = buys + sells, len(buys)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n):
        rng.shuffle(pooled)
        if statistics.mean(pooled[:k]) - statistics.mean(pooled[k:]) >= observed:
            hits += 1
    return observed, (hits + 1) / (n + 1)


def score(labels, watch, price_fn):
    tickers = {c["name"]: c["ticker"] for c in watch["companies"]}
    bench = price_fn(watch["benchmark"])
    series = {}
    rows = []
    for e in events(labels, tickers):
        sym = tickers[e["company"]]
        if sym not in series:
            series[sym] = price_fn(sym)
        rows.append({**e, **{f"x{h}": excess(series[sym], bench, e["date"], h) for h in HORIZONS}})
    return rows


def report(rows, labels):
    lines = ["# Score", "", f"Labels: {len(labels)}; buy/sell events: {len(rows)}", ""]
    routes = collections.Counter(r["route"] for r in labels)
    agreed = [r["agreed"] for r in labels if r.get("agreed") is not None]
    ms = sorted(r["ms"] for r in labels if r.get("ms") is not None)
    lines += [f"Router: routes {dict(routes)}; models agreed on {sum(agreed)}/{len(agreed)} observed; "
              f"median {ms[len(ms) // 2] if ms else '-'} ms", "",
              f"Labels: {dict(collections.Counter(r.get('label') for r in labels))}", "",
              "| horizon | side | events scored | mean excess | share beating benchmark |", "|---|---|---|---|---|"]
    for h in HORIZONS:
        for side in ("buy", "sell"):
            xs = [r[f"x{h}"] for r in rows if r["side"] == side and r[f"x{h}"] is not None]
            if xs:
                lines.append(f"| {h}d | {side} | {len(xs)} | {statistics.mean(xs) * 100:+.2f}% | "
                             f"{sum(x > 0 for x in xs) / len(xs):.0%} |")
            else:
                lines.append(f"| {h}d | {side} | 0 | - | - |")
    buys = [r[f"x{PRIMARY}"] for r in rows if r["side"] == "buy" and r[f"x{PRIMARY}"] is not None]
    sells = [r[f"x{PRIMARY}"] for r in rows if r["side"] == "sell" and r[f"x{PRIMARY}"] is not None]
    lines.append("")
    if len(buys) >= 2 and len(sells) >= 2:
        gap, p = permutation_p(buys, sells)
        lines.append(f"Primary ({PRIMARY}d buy minus sell): {gap * 100:+.2f} points, one-sided permutation "
                     f"p = {p:.3f} (n = {len(buys)} buy, {len(sells)} sell). Descriptive until the decision "
                     "point in PLAN.md.")
    else:
        lines.append("Primary: not enough scored events yet.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--prices", default=None, help="cache directory for price series")
    args = parser.parse_args()
    with open("watchlist.yml", encoding="utf-8") as handle:
        watch = yaml.safe_load(handle)
    path = Path(args.labels)
    labels = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
    rows = score(labels, watch, lambda s: closes(s, args.prices)) if labels else []
    text = report(rows, labels)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
