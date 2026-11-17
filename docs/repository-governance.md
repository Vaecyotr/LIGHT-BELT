# Repository Governance

## File classes

| Class | Location | Rule |
| --- | --- | --- |
| Authority | `CLAUDE.md`, `docs/CLOSED_LOOP_SPEC.md`, `docs/IMPLEMENTATION_PLAN.md` | Must describe current truth and may not silently conflict |
| Current guide | `docs/current/` | Must use current paths, models, and commands |
| Reference | `docs/reference/` | Stable user-facing API or feature reference |
| Acceptance | `docs/acceptance/`, `artifacts/baselines/` | Accepted evidence; normal tests do not rewrite it |
| History | `docs/history/` and existing fixture archives | Retain the minimum unique material with a current engineering use |
| Runtime output | `artifacts/runs/`, `output/`, build caches | Ignored by Git; inspect provenance and rescue unique evidence or inputs before cleanup |

## Lifecycle rules

1. Add new current documentation to `docs/current` or `docs/reference` and
   link it from `docs/README.md`.
2. Delete superseded files by default. Carry a still-needed contract, procedure,
   or field observation into the current maintained source. Keep the smallest
   useful record when its unique information is hard to recover and has a
   specific engineering use.
3. Keep acceptance inputs under `config/acceptance` while they verify a supported
   behavior. Keep fixed output evidence only when it is needed by a maintained
   verification or captures a measurement that is hard to repeat. Generate
   ordinary run output under `artifacts/runs/`.
4. Tests and ordinary scripts write only to pytest temporary directories or
   `artifacts/runs/`; maintained source belongs in its source/tool directory.
   Before cleaning ignored `artifacts/runs/` output, identify and preserve any
   unique evidence, source, or media in the local archive. Remove only output
   confirmed to be disposable; this is a cleanup precondition, not a script
   write-time check.
5. Keep generated protocol headers only when firmware builds consume them;
   their JSON golden vector remains the single source of truth.
6. Check actual loaders, external entry points, services, tests, and references
   before retiring files. Migrate any unique regression assertion to its active
   behavior test, then remove obsolete fixtures, scripts, and index entries as
   one change. Keep release license texts, notices, authorizations, and required
   source materials in their maintained distribution locations.

## Naming

- Use lowercase kebab-case for human-facing documents and configuration files.
- Include the schema or campaign version when it prevents ambiguity.
- Prefer purpose names such as `cabin-show-v2.yaml` over chronology-only names
  such as `V2_TO_V3.yaml`.
- Keep Python package filenames in the repository's existing snake_case style.
