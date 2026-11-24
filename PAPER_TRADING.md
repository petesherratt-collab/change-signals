# Paper trading rules (fixed 24 Nov 2026, before the first trade)

This is a report alongside the frozen test in PLAN.md, not part of it. It shows in
money what following the buy and sell labels would have done, after costs, next to
the same money in a FTSE 250 tracker. `tools/paper_trade.py` writes it to
`data/paper_trades.md` after every poll.

| Rule | Setting |
|---|---|
| What counts as a signal | Labels are netted per company per day, as in `score.py`: buys +1, sells −1. A net of zero is no signal. |
| Buy | £1,000 into the share at the first close strictly after the day the change was seen |
| Hold | 20 trading days, then sold at that day's close. Until then the trade is open, valued at the latest close. |
| Already held | A new buy for a company already held is skipped, so one story is not counted twice |
| Sell | Not traded. Short-selling small UK shares is not realistic for most people. Listed as "avoided", with what £1,000 would have done |
| Costs | 0.5% stamp duty on purchases; an assumed 0.5% dealing cost (spread and commission) each way |
| Comparison | The same £1,000, on the same dates, in a FTSE 250 tracker: no stamp duty, 0.1% dealing each way |
| Prices | Yahoo Finance daily closes, fetched fresh each run. A day counts only once the London market has closed (after 17:00 UTC). |

These rules are fixed now so they cannot be tuned to the results. A change to them
gets a dated note here, and the report is rebuilt from all labels under the new rules,
with both versions kept.

Not financial advice.
