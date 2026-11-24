# Amendment 2: 24 Nov 2026. Step B labels by majority vote

## What changes

Step B is the buy, sell or irrelevant question. Its label is now the **majority of
the valid model answers**, not the fastest one.

- A tie for the top answer gives "irrelevant". So does a split vote, so it never
  produces a trade signal.
- The fastest answer is still recorded (`b_first`), so the two rules can be
  compared.
- Every model's answer is still kept (`b_votes`).
- Disagreement still sets the uncertainty flag (`b_agreed` false).

Step A, the cosmetic question, is unchanged. It still answers time-first through the
router's fast path.

## Why

In the first labelled run (24 Nov, 14:15 UTC), Dunelm's careers churn of 23 Nov got
four "irrelevant" votes and one "sell". The fastest model was the one that said
"sell", so under the first-answer rule the label was "sell".

The router's time-first rule suits answers that someone is waiting for. A
once-a-day judgement that is scored weeks later gains nothing from being a few
seconds faster, and a single outlier model can create a trade signal.

## Which labels it applies to

- It applies to labels written after this commit.
- The **9 labels** already on the `data` branch were written under the
  first-answer rule. Data commit at this time: `b074009 2026-11-24T14:15:22+00:00`.
- Labels are append-only, so those 9 are kept as they are and are not relabelled.
  Records without `b_rule` were made under the old rule.
- Of the 9, only one label differs from what the majority would give: Dunelm
  careers, 23 Nov, labelled "sell" where the majority said "irrelevant". It is
  already flagged as disagreed.

## Scoring

`tools/score.py` is unchanged. Its hash is below and matches the frozen plan.

## SHA-256

    f6031d12144e084f6555c7ddcb67c43378395a7f66a018aa9558ca87643c616e  tools/label_changes.py
    411f3f7b7e405db991a2371d88e014f9f39666f670c2d3cd2dc1a85433f98a41  tools/score.py
