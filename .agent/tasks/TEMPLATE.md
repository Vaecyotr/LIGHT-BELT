# Phase Title

## Phase ID

phase-XX-short-name

## Goal

Describe the exact goal of this Phase in one or two sentences.

## Background

Explain why this Phase exists and what previous approved behavior must remain unchanged.

## In Scope

- Item 1
- Item 2
- Item 3

## Out of Scope

- Later Phase work
- Firmware unless explicitly approved
- Hardware verification unless real hardware is connected and tested
- Unrelated refactors
- Git commit, push, merge, tag, or PR creation

## Allowed Files

- path/to/file.py
- tests/test_something.py
- config/example.yaml

## Forbidden Files

- firmware/**
- docs/legacy/**
- Any file not required by this Phase

## Acceptance Criteria

- Criterion 1
- Criterion 2
- Criterion 3

## Required Targeted Tests

.\.python\Scripts\python.exe -m pytest tests/test_x.py -v

## Required Full Verification

.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat

## Required Report

The implementation or repair agent must report:

- Modified files
- What changed
- Tests added or updated
- Exact commands run
- Return codes
- Targeted test results
- Full test result
- Benchmark result if required
- git diff --stat
- Unresolved issues
- Suggested commit message

## Notes

Do not claim hardware verification unless real hardware was connected and tested.

