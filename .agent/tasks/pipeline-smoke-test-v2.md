# Dual-Agent Pipeline Smoke Test

## Phase ID

pipeline-smoke-test-v2

## Goal

Verify the complete Codex implementation, deterministic verification, Claude review, repair loop, and automatic Git commit workflow without changing application behavior.

## In Scope

- Create one repository-root smoke-test record.
- Preserve all existing application behavior.

## Out of Scope

- Runtime code changes
- Protocol changes
- Configuration changes
- Firmware changes
- Test weakening
- Hardware verification
- Main-branch modification or merge

## Allowed Files

- PIPELINE_SMOKE.md

## Forbidden Files

- light_engine/**
- tests/**
- config/**
- firmware/**
- AGENTS.md
- CLAUDE.md
- docs/**
- .agent/**

## Acceptance Criteria

- `PIPELINE_SMOKE.md` exists at the repository root.
- Its first line is exactly `# LIGHT-BELT Dual-Agent Pipeline Smoke Test`.
- It contains the exact line `status: automated-pipeline-ready`.
- It contains the exact line `application-code-changed: no`.
- It contains the exact line `hardware-verified: no`.
- No application, configuration, protocol, firmware, or test file is modified.
- Existing automated tests remain passing.

## Required Targeted Tests

```powershell
.\.python\python.exe -m pytest tests/test_models.py -q
```

## Required Full Verification

```powershell
.\.python\python.exe -m pytest -q
git diff --check
```

## Commit Message

chore: verify dual-agent pipeline

## Required Report

Report modified files, commands, return codes, test results, remaining limitations, and the suggested commit message.

## Notes

The new file must contain only:

```text
# LIGHT-BELT Dual-Agent Pipeline Smoke Test

status: automated-pipeline-ready
application-code-changed: no
hardware-verified: no
```
