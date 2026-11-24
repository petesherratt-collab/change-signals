# Amendment 1: 24 Nov 2026, before the first label

Written before any change was labelled: the `data` branch had no `labels.jsonl`
when this was committed. PLAN.md's scoring rules (`tools/score.py`) are unchanged.

## 1. Share-price lines are removed before a change is recorded

The first comparison of two polls (23 Nov) found 9 changes. Four of them came only
from share-price widgets embedded in the pages:

| Page | What changed |
|---|---|
| Hollywood Bowl board and news | "290.0p ▼ −0.17%" became "296.0p ▲ +2.07%" |
| Topps board and news | "33.90 / −0.70 / Share price at 20 Nov" became "33.60 / −0.30 / Share price at 23 Nov" |

A label made from such a change would be judging the very price move it is later
scored against. That would leak the outcome, and it is also not a signal about the
business.

`tools/extract_changes.py` (`FILTER_VERSION = 2`) now drops these lines before
comparing two polls:
- decimal prices;
- percentages;
- lines starting with ▲ or ▼;
- lines starting "Share price".

Whole numbers, such as a vacancy count, are kept. Changes are derived data, so they
were rebuilt from the untouched archive under the filter. The rebuild is refused
once labelling has begun.

## 2. Labelling is split into two steps

| Step | Question | How it is answered |
|---|---|---|
| A | Is this change cosmetic or routine? | Through the router's fast path with learning on. Agreed answers become examples, and code can be promoted when it reproduces them. |
| B | Buy, sell or irrelevant? | Only for changes that are not cosmetic. Raced across all models; never turned into code. The first valid answer is the label. Every model's answer is kept, and disagreement is the uncertainty flag. |

A cosmetic change is labelled "irrelevant". The record fields that `score.py` reads
(`label`, `route`, `agreed`, `ms`) are kept.

## 3. Router measures, fixed now

`tools/router_report.py` reports these by ISO week:
- how many changes there were;
- the share of step A answered by code;
- the share of step A where the models agreed;
- how many changes reached step B, and the share where the models agreed;
- the counts of buy, sell and irrelevant;
- the median time per change.

Cost comes from OpenRouter's usage page for the `change-signals` key.

**Router criterion, read once on 2027-01-05 (six weeks):** step A is answered by
promoted code for at least 25% of that week's changes, and at least 90% of the code
answers the router audits match the racing models' answer.

- Failing that is a finding, not a fault. The cosmetic question may simply not be
  rule-like enough to become code.
- Until the reading, the measures are descriptive only.

## 4. Polling

Scheduled runs were late. The 23 Nov 06:17 run started at 18:19, and no run had
started on 24 Nov by early afternoon.

A backup schedule was added at 13:47 UTC. Any scheduled run is skipped if a poll
happened in the last 20 hours, so a day gets one poll either way.

This does not change scoring: entry is still the first close strictly after the
poll's UTC date.

## Live check before committing

The new extraction and labelling were run once, locally, on the archive collected
up to 23 Nov (router `main`, live models). These labels were not committed. The
run in Actions labels the same changes again and becomes the record.

- 5 changes remained once the 4 price-widget changes were removed.
- Crest Nicholson ("gets green light for Longcross Garden Village") was labelled
  **buy**. All 5 models agreed.
- Topps and Dunelm vacancy churn was labelled **irrelevant**. All models agreed.
- Moonpig ("Holding(s) in Company" notice, new dates) was called cosmetic, but the
  models disagreed, so it is flagged.
- Marston's news was called cosmetic.

## SHA-256 of the files this amendment covers

    df9bf747341e36a3c67aa5944840551ce2482c9f2cdf532eb1aa81811d58c120  tools/extract_changes.py
    8d4f3678b9c3944047a9bdc767e19f3b0d4d6fc29121e6501c4ee48cfdd9873e  tools/label_changes.py
    fdcb45b2679d0bf21090e6607a2214ebf3e83fff4f71bb1761bc890f59794451  tools/router_report.py
    411f3f7b7e405db991a2371d88e014f9f39666f670c2d3cd2dc1a85433f98a41  tools/score.py
    b7e06e450aec1cb10dc8b3d527b756dda8b0cf62825d49b53aa98264735dc4da  .github/workflows/poll.yml
