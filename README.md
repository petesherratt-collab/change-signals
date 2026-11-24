# change-signals

Watches the careers, board and news pages of 25 smaller UK-listed companies,
once a day. The aim is to see whether the changes on those pages say anything
about the share price.

The project combines two of the owner's projects:

- [evidence-archive](https://github.com/petesherratt-collab/evidence-archive)
  collects the pages. Each record is hash-chained, so a label provably came
  before the price it is scored against.
- [Adaptive_Router](https://github.com/petesherratt-collab/Adaptive_Router)
  labels each change buy, sell or irrelevant. It races models, and moves the
  labelling into code where the models agree.

It is paper only, and the rules are frozen in [`PLAN.md`](PLAN.md).

## Pipeline (`.github/workflows/poll.yml`, daily 06:17 UTC)

1. `tools/build_config.py` writes `kibitzr.yml` from the verified pages in
   `watchlist.yml`. Then `kibitzr once` polls every page into `data/archive`,
   and `kibitzr archive verify` checks the chains.
2. `tools/extract_changes.py` re-derives each page's selected text from the
   retained raw responses, with each blob checked against its hash. It writes
   one record per change, with the removed and added lines, to
   `data/changes.jsonl`.
3. `tools/label_changes.py` labels new changes through the router into
   `data/labels.jsonl`. It needs the `OPENROUTER_API_KEY` repository secret;
   without it, labelling is skipped and collection carries on.
4. `tools/score.py` scores buy and sell labels old enough to have 5- and
   20-day prices, and writes `data/score.md`.
5. The run commits everything to the `data` branch.

## Before collection: probing (`.github/workflows/probe.yml`, manual)

- `discover` finds candidate careers, board and news pages from each site's
  home page. It also reports robots.txt and redirects.
- `verify` fetches each listed page twice and reports whether the selected text
  is stable.

Pages enter `watchlist.yml` only after `verify` passes.

## Cost

About 100 checks a day. Labelling costs about $0.002 per change at today's
prices (five models raced), and nothing once a change type has become code.
If 10 to 20 changes a day survive, that is roughly $1 to $2 a month. GitHub
Actions minutes for a private repository fall within the free allowance.

## Paper trading

`tools/paper_trade.py` turns the same labels into a pretend account after each poll:
£1,000 per buy, held 20 trading days, with stamp duty and dealing costs, against the
same money in a FTSE 250 tracker. Sells are listed as avoided. The rules are in
[`PAPER_TRADING.md`](PAPER_TRADING.md), and the latest report is
`paper_trades.md` on the `data` branch. It sits alongside the frozen test, not in place of it.
