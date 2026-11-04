# Repository Governance

## File classes

| Class | Location | Rule |
| --- | --- | --- |
| Authority | `CLAUDE.md`, `docs/CLOSED_LOOP_SPEC.md`, `docs/IMPLEMENTATION_PLAN.md` | Must describe current truth and may not silently conflict |
| Current guide | `docs/current/` | Must use current paths, models, and commands |
| Reference | `docs/reference/` | Stable user-facing API or feature reference |
| Acceptance | `docs/acceptance/`, `artifacts/baselines/` | Accepted evidence; normal tests do not rewrite it |
| History | `docs/history/`, `.agent/archive/`, `.claude/archive/` | Preserved provenance; never used as current instruction |
| Runtime output | `artifacts/runs/`, `output/`, build caches | Ignored by Git; inspect provenance and rescue unique evidence or inputs before cleanup |

## Lifecycle rules

1. Add new current documentation to `docs/current` or `docs/reference` and
   link it from `docs/README.md`.
2. When a guide is superseded, move it to `docs/history` instead of leaving two
   active-looking copies.
3. Put acceptance inputs under `config/acceptance` and accepted outputs under
   `artifacts/baselines`.
4. Tests and ordinary scripts write only to pytest temporary directories or
   `artifacts/runs/`; maintained source belongs in its source/tool directory.
   Before cleaning ignored `artifacts/runs/` output, identify and preserve any
   unique evidence, source, or media in the local archive. Remove only output
   confirmed to be disposable; this is a cleanup precondition, not a script
   write-time check.
5. Keep generated protocol headers only when firmware builds consume them;
   their JSON golden vector remains the single source of truth.
6. Delete a file only after confirming it is generated, accidental, or both
   unreferenced and redundant. Git history is not a substitute for an active
   archive when the material explains an accepted contract.

The completed 2026-07-13 migration and its review boundaries are recorded in
`docs/acceptance/repository-governance-closeout.md`.

## Naming

- Use lowercase kebab-case for human-facing documents and configuration files.
- Include the schema or campaign version when it prevents ambiguity.
- Prefer purpose names such as `cabin-show-v2.yaml` over chronology-only names
  such as `V2_TO_V3.yaml`.
- Keep Python package filenames in the repository's existing snake_case style.
