# Current Implementation Plan

Status: **completed through Step 6 on 2026-07-13; stop boundary reached**.

Product implementation Phases 0-29 are complete. Their original approved plan
is preserved at
`docs/history/implementation/implementation-plan-phases-0-29.md` and is no
longer an active instruction source.

## Approved scope

1. Inventory and classify repository files.
2. Establish one current documentation entry point.
3. Archive completed plans, task files, campaign manifests, and legacy docs.
4. Separate committed acceptance baselines from disposable run output.
5. Organize configuration by runtime, profile, show, example, and acceptance
   purpose; improve ambiguous filenames.
6. Remove only confirmed accidental, broken, or ad-hoc duplicate files, then
   stop.

## Boundaries

- Do not change wire formats, topology, safety behavior, brightness ownership,
  sequence ownership, or production transport semantics.
- Preserve all user work already present in the working tree.
- Prefer archival moves over deleting historical documentation.
- Do not begin a later product Phase as part of this maintenance work.
- Keep physical behavior labeled **NOT HARDWARE VERIFIED**.

## Completion gates

- Root and documentation indexes point only to current paths.
- Archived material is clearly separated from active instructions.
- Full pytest no longer changes committed acceptance baselines or reports.
- Config and document references resolve after moves.
- The full test suite and required benchmark pass.
- Firmware builds pass if the configured PlatformIO environment remains
  available.

All gates above passed in the completion audit. No later product or cleanup
phase is approved by this plan.
