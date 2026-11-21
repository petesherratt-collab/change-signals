# Change signals V1: plan (frozen before the first collected poll)

**Question.** Changes to UK-listed companies' own web pages may carry signals
about the business. When a router labels each change buy, sell or irrelevant,
do the buy and sell labels predict the share price relative to the market?
Two sub-questions:

- **Router:** how much of the labelling turns into code?
- **Uncertainty:** does model disagreement mark the weaker labels?

**Status.** This is paper only: no money is placed on any label. Nothing in
this repository is investment advice.

## Collection

- **Watchlist.** 25 companies, listed in `watchlist.yml`, with the careers,
  board and news pages of each.
- **Admission rule.** A page is admitted only after `tools/probe.py verify`
  shows all four of:
  - HTTP 200 with no redirect to another site;
  - robots.txt allows the page;
  - the selected text is the same across two fetches;
  - the size is acceptable.

  A company with no admissible page is dropped and the reason noted here.
- **Polling.** One poll a day at 06:17 UTC, by `.github/workflows/poll.yml`,
  into a `kibitzr-archive` archive. The archive holds:
  - a poll log that also records unchanged polls;
  - the raw responses;
  - hash chains, on the `data` branch.

  The user agent identifies the archive.
- **Selector changes.** A selector changed after collection starts is recorded
  on the archive's annotation chain. Its changes are reported separately from
  that point on.

## Labelling (fixed)

- **What is labelled.** Every change in the selected text, as removed and
  added lines (`tools/extract_changes.py`).
- **How.** Through the Adaptive Router fast path (`tools/label_changes.py`),
  with the spec and signature fixed in that file. Learning is on, so
  agreed answers may become code.
- **What each label records:**
  - the route (code or model);
  - the model;
  - the time taken;
  - whether the racing models agreed.
- **Timing.** A label is written in the same run as the poll that found the
  change, before any later price exists. The data branch's commit history is
  the record of that order.

## Scoring (fixed: `tools/score.py`)

- **Events.** Buy and sell labels are netted per company per poll date
  (buy +1, sell −1). A net of zero drops the event.
- **Entry.** The first trading-day close strictly after the poll's UTC date.
- **Excess return.** The stock's return minus the FTSE 250's (^FTMC) over the
  same closes, at 5 and 20 trading days. Prices come from Yahoo Finance's
  daily chart data.
- **Primary statistic.** The mean 20-day excess return of buy events minus the
  mean of sell events.
- **Test.** One-sided permutation test: 10,000 shuffles, seed 20261121.
- **Secondary results:**
  - the same statistic on agreed labels only;
  - the 5-day horizon;
  - the share of each side beating the benchmark;
  - router measures: share of labels by code, median time, and agreement
    rate.

## Decision point

The primary test is read **once**: at 100 scored buy-plus-sell events at
20 days, or on 2027-06-30, whichever comes first. Before then every output is
descriptive.

**Pass:** the primary statistic is above zero with p < 0.05.

**Otherwise:** the result is "no evidence of a signal", which is the expected
outcome and a finding in itself.

The router questions are answered descriptively from the first month.

## Known weaknesses, stated in advance

- **Few events.** The sample will be small, and 25 companies in a few sectors
  move together, so events are not independent. A permutation test over
  events overstates the evidence when they cluster in time.
- **No costs.** The benchmark is an index, and there are no trading costs or
  spreads. Small companies' spreads can exceed any effect found.
- **Selection.** The companies, page kinds and labelling spec were chosen by
  the experimenter before data. They are fixed here so they cannot be chosen
  after it.
