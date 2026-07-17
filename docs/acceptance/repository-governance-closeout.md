# Repository Governance Closeout

Date: 2026-07-13
Scope: repository governance Steps 1-6
Status: complete; freeze requested after the unstaged audit

This record was prepared against the large unstaged working tree after the
repository governance pass. It distinguishes path migrations, approved
deletions, and feature work that already existed before governance began. At
the time of the audit it was a review aid rather than permission to stage or
commit; the user subsequently requested a local baseline freeze.

## Baseline and preservation evidence

- The required repository interpreter resolved to
  `.python/Scripts/python.exe` and imported `light_engine` from this worktree.
- The pre-closeout full suite passed: `557 passed in 135.42s`.
- Committed acceptance evidence was compared with the pre-governance backup:
  `PREEXISTING_BASELINES_PRESERVED`.
- Full pytest was previously verified not to change `artifacts/baselines/` or
  `docs/acceptance/`.
- Markdown links, active stale-path searches, archived manifest task paths,
  `git diff --check`, the benchmark, and both firmware builds passed in the
  Step 6 completion audit.

## Why Git currently shows many deletions

The worktree is intentionally not staged. Git reports 109 tracked old paths as
deleted and 126 destination/new files as untracked. Most of those pairs are
moves that Git can recognize as renames only after staging. The current
`git diff --stat` therefore counts old-path removals but omits untracked
destinations; it is not a reliable measure of lost content.

## Agent and campaign migrations

| Previous path | Current path |
| --- | --- |
| `.agent/campaigns/closed-loop-v2.json` | `.agent/archive/campaigns/closed-loop-v2/campaign.json` |
| `.agent/campaigns/show-orchestration-v1.json` | `.agent/archive/campaigns/show-orchestration-v1/full-campaign.json` |
| `.agent/campaigns/show-orchestration-v1-a-foundation.json` | `.agent/archive/campaigns/show-orchestration-v1/foundation.json` |
| `.agent/campaigns/show-orchestration-v1-b-runtime.json` | `.agent/archive/campaigns/show-orchestration-v1/runtime.json` |
| `.agent/campaigns/show-orchestration-v1-c-music.json` | `.agent/archive/campaigns/show-orchestration-v1/music.json` |
| `.agent/campaigns/show-orchestration-v1-d-acceptance.json` | `.agent/archive/campaigns/show-orchestration-v1/acceptance.json` |
| `.agent/campaigns/authoring-modulation-v1.json` | `.agent/archive/campaigns/authoring-modulation-v1/campaign.json` |
| `.agent/campaigns/authoring-modulation-v1-continue.json` | `.agent/archive/campaigns/authoring-modulation-v1/continuation.json` |
| `.agent/campaigns/cabin-lighting-v2.json` | `.agent/archive/campaigns/cabin-lighting-v2/campaign.json` |
| `.agent/tasks/phase-4...phase-10` | `.agent/archive/tasks/closed-loop-v2/` |
| `.agent/tasks/phase-11...phase-17` and `phase-16x` | `.agent/archive/tasks/show-orchestration-v1/` |
| `.agent/tasks/phase-18...phase-23` | `.agent/archive/tasks/authoring-modulation-v1/` |
| `.agent/tasks/phase-24...phase-29` | `.agent/archive/tasks/cabin-lighting-v2/` |
| `.agent/tasks/pipeline-smoke-test*.md` | `.agent/archive/tasks/pipeline/` |
| `.claude/skills/build-lighting-prototype/SKILL.md` | `.claude/archive/skills/build-lighting-prototype-v1/SKILL.md` |

Archived manifests now point to archived task paths. The generic campaign
runner requires an explicit `--manifest`; no historical campaign is selected
by default. Prompts, schemas, and `.agent/tasks/TEMPLATE.md` remain active.

## Documentation migrations

### Current and reference material

| Previous path | Current path |
| --- | --- |
| `docs/CABIN_LIGHTING_V3_OPERATOR_GUIDE.md` | `docs/current/cabin-lighting-v3-operator-guide.md` |
| `docs/ESP32_WINDOWS_COMMISSIONING.md` | `docs/current/esp32-windows-commissioning.md` |
| `docs/show_306/SHOW_V2_AUTHORING.md` | `docs/current/show-v2-authoring.md` |
| `docs/EFFECT_REFERENCE.md` | `docs/reference/effect-reference.md` |
| `docs/host_api_v1.md` | `docs/reference/host-api-v1.md` |
| `docs/host_api_v1.openapi.yaml` | `docs/reference/host-api-v1.openapi.yaml` |
| `docs/host_api_v1_changelog.md` | `docs/reference/host-api-v1-changelog.md` |

### Acceptance records

| Previous path | Current path |
| --- | --- |
| `docs/acceptance_report.md` | `docs/acceptance/closed-loop-v2-software-acceptance.md` |
| `docs/show_acceptance_report.md` | `docs/acceptance/show-orchestration-v1-software-acceptance.md` |
| `docs/authoring_modulation_acceptance_report.md` | `docs/acceptance/authoring-modulation-v1-software-acceptance.md` |
| `docs/cabin_v3_acceptance_report.md` | `docs/acceptance/cabin-lighting-v3-software-acceptance.md` |
| `docs/SHOW_ORCHESTRATION_V1_SOFTWARE_ACCEPTANCE_CHECKPOINT.md` | `docs/acceptance/show-orchestration-v1-checkpoint.md` |
| `docs/SHOW_HARDWARE_ACCEPTANCE_CHECKLIST.md` | `docs/acceptance/hardware-acceptance-checklist.md` |

### Historical material

| Previous path or group | Current path |
| --- | --- |
| Original `docs/IMPLEMENTATION_PLAN.md` Phase 0-29 body | `docs/history/implementation/implementation-plan-phases-0-29.md` |
| `docs/SHOW_ORCHESTRATION_V1_PLAN.md` | `docs/history/campaigns/show-orchestration-v1/plan.md` |
| `docs/REPORT_ADOPTION.md` | `docs/history/campaigns/show-orchestration-v1/report-adoption.md` |
| `REVIEW_AND_CHANGES.md` | `docs/history/campaigns/show-orchestration-v1/revision-audit.md` |
| Historical body of `INSTALL_AND_RUN.md` | `docs/history/campaigns/show-orchestration-v1/install-and-run.md` |
| `docs/contracts/*` | `docs/history/campaigns/show-orchestration-v1/contracts/` |
| `docs/show_306/AUTHORING_AND_HOST_API_V1_ALIGNMENT.md` | `docs/history/campaigns/authoring-modulation-v1/host-api-v1-alignment.md` |
| `docs/archive/host_api_*` | `docs/history/host-api-candidates/` |
| `docs/algorithms.md`, `architecture.md`, `configuration.md` | `docs/history/legacy-prototype/` |
| `docs/hardware-integration.md`, `protocol.md`, `rk3588_deployment.md` | `docs/history/legacy-prototype/` |
| Five Chinese prototype guides | `docs/history/legacy-prototype/` |

New current entry points are `README.md`, `INSTALL_AND_RUN.md`,
`docs/README.md`, and `docs/repository-governance.md`. The active
`docs/IMPLEMENTATION_PLAN.md` records only the completed six-step governance
scope and its stop boundary.

## Configuration migrations

| Previous path | Current path |
| --- | --- |
| `config/show.cabin-v2.yaml` | `config/shows/cabin-show-v2.yaml` |
| `config/V2_TO_V3.yaml` | `config/shows/cabin-commissioning-show-v2.yaml` |
| `config/show.cabin-fork-example.yaml` | `config/examples/cabin-show-fork-v2.yaml` |
| `config/show.example.yaml` | `config/examples/teacher-demo-show-v2.yaml` |
| `config/show.minimal.example.yaml` | `config/examples/minimal-show-v1.yaml` |
| `config/virtual_paths.example.yaml` | `config/examples/virtual-paths.yaml` |
| `config/show_acceptance.yaml` | `config/acceptance/show-orchestration-v1/show.yaml` |
| `config/layout_acceptance.yaml` | `config/acceptance/show-orchestration-v1/layout.yaml` |
| `config/show_authoring_modulation_acceptance.yaml` | `config/acceptance/authoring-modulation-v1/show.yaml` |
| `config/layout_authoring_modulation_acceptance.yaml` | `config/acceptance/authoring-modulation-v1/layout.yaml` |
| `config/cabin_v3_acceptance.yaml` | `config/acceptance/cabin-lighting-v3/topology.yaml` |
| `config/profiles/cabin_lighting_v3_production.yaml` | `config/profiles/cabin-lighting-v3-production.yaml` |
| `config/profiles/cabin_lighting_v3_site_local.yaml` | `config/profiles/cabin-lighting-v3-site-local.yaml` |
| `config/profiles/rk3588_production.yaml` | `config/profiles/rk3588-production.yaml` |
| `config/profiles/windows_dev.yaml` | `config/profiles/windows-development.yaml` |

The four default loader inputs remain at `config/system.yaml`, `layout.yaml`,
`effects.yaml`, and `outputs.yaml`. No runtime loading convention was changed
for cosmetic reasons.

## Acceptance artifact migrations

| Previous directory | Current directory |
| --- | --- |
| `artifacts/show_acceptance/` | `artifacts/baselines/show-orchestration-v1/` |
| `artifacts/authoring_modulation_acceptance/` | `artifacts/baselines/authoring-modulation-v1/` |
| `artifacts/cabin_v3_acceptance/` | `artifacts/baselines/cabin-lighting-v3/` |

Normal acceptance runs now default to ignored `artifacts/runs/`; pytest passes
its own temporary directory. The accepted baseline bytes were preserved.

## Script migration

`scripts/verify_show_orchestration_baseline.py` moved to
`scripts/archive/show-orchestration-v1/verify-baseline.py`. It remains usable
for historical evidence, while the active scripts directory contains reusable
pipeline and acceptance tooling.

## Approved deletions

The following files were removed rather than archived because they were
confirmed accidental, broken, or ad-hoc duplicates:

- `t -q`: captured `less` help output accidentally committed as a file.
- `01_demo_fixed.bat` and the six numbered Chinese `.bat` launchers: all used
  the nonexistent `.python/python.exe`; one also contained invalid doubled
  percent expansion.
- `light_engine.zip`: untracked source snapshot containing `__pycache__`.
- `scripts.zip`: untracked source snapshot containing a `.bak` file.

The two ZIP files remain recoverable from the ignored pre-governance backup.

## Work that existed before governance

The following feature and commissioning changes were already modified or
untracked when governance began. They were preserved and must not be mistaken
for new governance implementation:

- New `color_wipe` and `twinkle` effects, registry/base changes, effect config,
  and their tests.
- Show v2 effect-authoring tests and documentation changes.
- ESP32 LED output changes, node-specific headers, local-config example, and
  site node configuration tests.
- Generated RS-485/UDP golden headers that were already modified.
- The site-local cabin profile, commissioning Show, cabin fork example,
  effect reference, and ESP32 Windows commissioning guide.
- Modified acceptance summaries that now reside under
  `artifacts/baselines/`.

Some current files contain both categories. For example,
`tests/test_show_v2.py` contains pre-existing Show work plus governance path
updates, and the current operator/commissioning guides contain pre-existing
instructions plus new documentation locations.

## Review and commit boundaries

Two review sets are useful:

1. **Feature/commissioning set**: effects, ESP32 output/node configs, site
   profile, commissioning Show, effect documentation, and their tests.
2. **Governance set**: path migrations, indexes, archive boundaries,
   acceptance run isolation, active-reference updates, and confirmed deletes.

They are review categories, not automatically safe commits. Reconstructing two
independently green commits would require an explicit temporary index or
worktree because several files contain both sets. Without that reconstruction,
one atomic green commit is safer than creating an intermediate commit with
broken paths or missing documentation.

No files had been staged or committed when this audit was prepared. The user
subsequently approved a local freeze commit; its SHA is reported by the task
that creates the baseline rather than embedded here.
