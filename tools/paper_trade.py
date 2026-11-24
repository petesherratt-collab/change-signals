"""Paper trading: what following the labels would have done to a pretend account, after costs.

    python tools/paper_trade.py --labels data/labels.jsonl --out data/paper_trades.md

A report alongside the frozen test in PLAN.md, not part of it. The rules are fixed
here, before the first trade, and written up in PAPER_TRADING.md:

- Each buy event (labels netted per company per day, as in score.py) puts £1,000 into
  the share at the first close strictly after the day the change was seen.
- It is sold at the close 20 trading days later. Until then it is open, valued at the
  latest close.
- A buy for a company already held is skipped, so one story is not counted twice.
- Costs: 0.5% stamp duty on purchases and an assumed 0.5% dealing cost (spread and
  commission) each way.
- A sell event is not traded. Short-selling these shares is not realistic for most
  people. It is listed as "avoided", with what £1,000 would have done over the same
  20 days.
- The comparison is the same £1,000, on the same dates, in a FTSE 250 tracker: no
  stamp duty and 0.1% dealing each way.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import yaml

import score

STAKE = 1000.0
HOLD = 20                 # trading days
STAMP = 0.005             # UK stamp duty on share purchases
DEAL = 0.005              # assumed spread + commission, each way, small-company shares
TRACKER_DEAL = 0.001      # index tracker dealing, each way; no stamp duty


def completed(series, now=None):
    """Drop today's bar until the London market has closed (16:35 UK; 17:00 UTC is safe all year):
    a price fetched mid-session is not a close."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.hour >= 17:
        return series
    return [(d, p) for d, p in series if d < now.date()]


def leg(series, when, hold=HOLD):
    """(entry_day, entry_price, exit_day, exit_price, closed) from the first close after ``when``; None if not yet entered."""
    after = [i for i, (d, _) in enumerate(series) if d > when]
    if not after:
        return None
    i = after[0]
    j = min(i + hold, len(series) - 1)
    return series[i][0], series[i][1], series[j][0], series[j][1], i + hold <= len(series) - 1


def value(stake, entry, exit_, buy_costs, sell_cost):
    """Money back after buying ``stake`` worth at ``entry`` and selling at ``exit_``, costs taken."""
    shares = stake * (1 - buy_costs) / entry
    return shares * exit_ * (1 - sell_cost)


def bench_on(bench, day):
    prices = dict(bench)
    if day in prices:
        return prices[day]
    earlier = [p for d, p in bench if d <= day]
    return earlier[-1] if earlier else None


def trades(labels, watch, price_fn):
    tickers = {c["name"]: c["ticker"] for c in watch["companies"]}
    bench = price_fn(watch["benchmark"])
    series, held_until, rows = {}, {}, []
    for e in score.events(labels, tickers):
        sym = tickers[e["company"]]
        if sym not in series:
            series[sym] = price_fn(sym)
        l = leg(series[sym], e["date"])
        row = {"company": e["company"], "side": e["side"], "seen": e["date"]}
        if l is None:
            rows.append({**row, "status": "waiting for next close"})
            continue
        entry_day, entry, exit_day, exit_, closed = l
        b_entry, b_exit = bench_on(bench, entry_day), bench_on(bench, exit_day)
        tracker = value(STAKE, b_entry, b_exit, TRACKER_DEAL, TRACKER_DEAL) if b_entry and b_exit else None
        row.update({"entry_day": entry_day, "entry": entry, "exit_day": exit_day, "exit": exit_,
                    "closed": closed, "tracker": tracker})
        if e["side"] == "sell":
            row.update({"status": "avoided", "back": value(STAKE, entry, exit_, STAMP + DEAL, DEAL)})
        elif e["company"] in held_until and entry_day <= held_until[e["company"]]:
            row.update({"status": "skipped: already held", "back": None})
        else:
            held_until[e["company"]] = exit_day
            row.update({"status": "closed" if closed else "open", "back": value(STAKE, entry, exit_, STAMP + DEAL, DEAL)})
        rows.append(row)
    return rows


def money(v):
    return "-" if v is None else (f"£{v:,.2f}" if v >= 0 else f"−£{-v:,.2f}")


def report(rows):
    traded = [r for r in rows if r["status"] in ("open", "closed")]
    pnl = sum(r["back"] - STAKE for r in traded)
    tracker = sum(r["tracker"] - STAKE for r in traded if r.get("tracker") is not None)
    closed = [r for r in traded if r["status"] == "closed"]
    lines = [
        "# Paper trades",
        "",
        f"£{STAKE:,.0f} per buy, held {HOLD} trading days; {STAMP:.1%} stamp duty and {DEAL:.1%} dealing each way. "
        "Sells are not traded; they are listed as avoided. Rules: PAPER_TRADING.md. Not part of the frozen test in PLAN.md.",
        "",
        f"**Trades:** {len(traded)} ({len(closed)} closed, {len(traded) - len(closed)} open) · "
        f"**Money in:** {money(STAKE * len(traded))} · **Profit/loss after costs:** {money(pnl)} · "
        f"**Same money in a FTSE 250 tracker:** {money(tracker)} · **Difference:** {money(pnl - tracker)}",
        "",
        "| seen | company | label | status | entry | price in | valued / sold | price | back after costs | P&L | tracker P&L |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (r["seen"], r["company"])):
        if "entry_day" not in r:
            lines.append(f"| {r['seen']} | {r['company']} | {r['side']} | {r['status']} | | | | | | | |")
            continue
        back = r.get("back")
        lines.append(
            f"| {r['seen']} | {r['company']} | {r['side']} | {r['status']} | {r['entry_day']} | {r['entry']:,.2f} | "
            f"{r['exit_day']} | {r['exit']:,.2f} | {money(back)} | {money(back - STAKE if back is not None else None)} | "
            f"{money(r['tracker'] - STAKE if r.get('tracker') is not None else None)} |")
    lines += ["", "Prices are Yahoo Finance daily closes (UK shares in pence). Open trades are valued at the latest close."]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with open("watchlist.yml", encoding="utf-8") as handle:
        watch = yaml.safe_load(handle)
    path = Path(args.labels)
    labels = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
    # fetched fresh (no same-day cache), so "today" is judged against the time of this fetch
    rows = trades(labels, watch, lambda s: completed(score.closes(s, None))) if labels else []
    text = report(rows)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
