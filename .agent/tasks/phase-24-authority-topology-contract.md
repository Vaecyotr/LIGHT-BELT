# Phase 24 — Authority and Topology Contract

## Phase ID

phase-24-authority-topology-contract

## Goal

Replace obsolete installation assumptions in the authoritative documents with the approved cabin topology, naming rules, provisional controller allocation, and explicit hardware-verification boundary. This Phase changes contracts and documentation only.

## Background

The cabin is 2100 mm × 1000 mm × 1800 mm. It contains 14 physical light runs: 13 independent 24 V WS2811 strips and one 24 V common-anode RGB+CCT COB run. The physical labels are 11, 12, 21, 22, 31, 32, 41, 42, 43, 44, 45, 91, 92, and 93; only 32 is not WS2811. Existing documents still describe six analog zones and one concatenated digital-node payload, so implementation must not begin until authority is aligned.

## Binding Contract References

- `AGENTS.md`
- User-approved cabin-lighting-v2 plan captured in this Task
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Update `CLAUDE.md`, `docs/CLOSED_LOOP_SPEC.md`, and `docs/IMPLEMENTATION_PLAN.md` so they agree.
- Record placement: 11/21/31/41 surround the screen; 12 is the ceiling edge; 22 is the floor/wall edge; 32 is the left porthole/door COB; 42-45 are right-wall waves; 91-93 are reserved/removable installation runs.
- Record lengths and WS2811 groups: 12/22 are 2 m and 40 groups each; 42/43/44/45/91/92/93 are 1 m and 20 groups each; 11/21/31/41 are 0.5 m and 10 groups each; total digital groups are 260.
- Lock logical IDs as `strip_<physical-label>` and `zone_32`. State that physical label, logical ID, ESP32 node ID, GPIO, protocol node ID, and Host API target ID are distinct concepts.
- Lock the provisional five-node mapping: node 1 GPIO4/5/6 → 11/21/31; node 2 → 41/42/43; node 3 → 44/45/93; node 4 → 12/91/92; node 5 GPIO4 → 22 with GPIO5/6 unused.
- State that `zone_32` uses one configurable STM32 RS-485 node and physical label 32 is not its forced bus address.
- Record the electrical plan: independent data pins through SN74LVC1T45, 24 V parallel strip power, 5 V B-side logic supply, and mandatory common ground.
- Mark every untested hardware/topology statement `NOT HARDWARE VERIFIED` and keep mapping values configurable.

## Out of Scope

- Production code, tests, config, protocols, firmware, generated artifacts, or Host API changes.
- Claiming the provisional five-node allocation is final wiring.
- Deleting legacy documents that retain historical value.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- CLAUDE.md
- docs/CLOSED_LOOP_SPEC.md
- docs/IMPLEMENTATION_PLAN.md
- docs/hardware-integration.md

## Forbidden Files

- light_engine/**
- firmware/**
- config/**
- tests/**
- artifacts/**
- .agent/**
- scripts/**

## Binding Quality Constraints

- Authority documents MUST contain no remaining claim that the target installation has six analog zones or one concatenated 300-pixel strip.
- `DigitalStrip` MUST remain hardware-agnostic; physical allocation belongs to mapping/config/protocol/firmware layers.
- Historical material may remain only when clearly labeled legacy or superseded.
- The report MUST include a requirement-to-document traceability table and exact command return codes.

## Acceptance Criteria

- All three authority documents agree on 13 WS2811 strips, one RGB+CCT COB, 260 digital groups, machine IDs, and provisional five-node allocation.
- The documents explicitly preserve independent strip outputs and one complete multi-output frame per ESP32 refresh.
- Unknown final wiring, IP addresses, power segmentation, and real synchronization performance are marked configurable and `NOT HARDWARE VERIFIED`.

## Required Targeted Tests

```powershell
rg -n "260|strip_41|zone_32|NOT HARDWARE VERIFIED|GPIO4" CLAUDE.md docs/CLOSED_LOOP_SPEC.md docs/IMPLEMENTATION_PLAN.md
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
git status --short
git diff --stat
```

## Required Report

Report modified files, authority conflicts removed, topology/naming tables added, exact commands and return codes, test count/time, traceability, unresolved wiring decisions, `NOT HARDWARE VERIFIED` items, and `git diff --stat`.

## Commit Message

Phase 24: Lock cabin topology and naming contracts
