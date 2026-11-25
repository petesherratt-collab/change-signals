# Amendment 3: 25 Nov 2026. Probation for promoted code in step A

## What changes

The Adaptive Router's single-step fast path, which step A ("is this change
cosmetic?") runs on, gains **probation**:

- every answer of a newly promoted function is audited until it has served 10 answers;
- after that, the usual sample of 1 in 10 is audited;
- a function that disagrees with an agreed audit answer is demoted, and step A goes back
  to racing models until a new function passes.

This repository runs the router from its `main` branch. The change applies from the
first poll after the router change reaches that branch.

## Why it is recorded here

Amendment 1's router criterion, read on 2027-01-05, counts how often promoted code
answers step A and how often the audited code answers match the racing models.
Probation audits more of a new function's answers, so it changes how many audits there
are. It does not change what an audit is.

## State when this was written

- Step A had 21 agreed examples.
- **No function had been promoted.**
- No code answer had been served or audited.

No data collected so far is affected.

The criterion stands unchanged: step A answered by promoted code for at least 25% of
that week's changes, with at least 90% of audited code answers matching. Probation's
audits count as audits.
