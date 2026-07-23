# Acceptance Artifacts

- `baselines/` contains committed evidence from accepted software campaigns.
- `runs/` contains disposable output from local executions and is ignored.

Do not update a baseline as a side effect of pytest. Regeneration and adoption
of a new baseline must be an explicit, reviewable task.
