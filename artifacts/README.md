# Acceptance Artifacts & Baselines

This directory manages the machine-readable evidence outputs generated during software acceptance campaigns.

## Acceptance Evidence Lifecycle

The repository enforces a strict 5-stage separation between test inputs, execution outputs, committed baselines, and human reports:

```
[config/acceptance/] (Fixed, immutable acceptance inputs & fixtures)
       │
       ▼
[Execution Engine / Pytest / Scripts] (Offline deterministic renderers, benchmark scripts)
       │
       ├─────────────────────────────────────────┐
       ▼                                         ▼
[artifacts/runs/] (Local run output)           [artifacts/baselines/] (Committed accepted software evidence)
    • Git-ignored                                  • Machine-readable JSON/JSONL
    • Inspect provenance before cleanup             • Deterministic SHA-256 hashes & metrics
    • NOT a baseline                               • Never updated as pytest side-effect
                                                 │
                                                 ▼
                                     [docs/acceptance/] (Human-readable acceptance records)
                                         • Summary tables, traceability matrix
                                         • Explicit command outputs & environment records
                                         • Mandatory "NOT HARDWARE VERIFIED" disclaimers
```

### Governance Invariants

Unique evidence and recovery material is preserved under the ignored
`artifacts/local-archives/` tree. See
`artifacts/local-archives/workspace-governance/` for the current
workspace-governance archive.

1. **No Silent Baseline Mutation**: Running `pytest` or ad-hoc scripts must **NEVER** overwrite files in `baselines/`. Adopting a new baseline is an explicit, reviewable task.
2. **Runs ≠ Baselines**: Files in `runs/` are ignored local run output, not accepted baselines. Before cleanup, identify and archive any unique source, evidence, or media; only confirmed disposable output may be removed.
3. **Software Evidence ≠ Hardware Proof**: Machine evidence in `baselines/` validates software determinism and engine capacity; it does not prove physical hardware or field electrical timing unless accompanied by real physical measurements.
4. **Directory Names ≠ Current Topology Authority**: Baseline directory names preserve the historical campaign identifier under which evidence was gathered. Canonical production topology authority resides in [CLAUDE.md](../CLAUDE.md) and [config/profiles/rk3588-host-service.yaml](../config/profiles/rk3588-host-service.yaml).

## Artifact Directory

| Path | Type | Status | Purpose | Authority / evidence role | Who should read | Do not use it for |
|---|---|---|---|---|---|---|
| [baselines/authoring-modulation-v1/](baselines/authoring-modulation-v1/) | `ACCEPTED BASELINE` | `ACCEPTED SOFTWARE EVIDENCE` | Machine-readable JSON evidence (`manifest.json`, `summary.json`, `two_run_digests.json`, `sample_evidence.json`) for 180-frame deterministic render, RGB samples, cue modulation bounds, and transition weights. | Software acceptance evidence for Phase 22; software contract (does not constitute hardware verification). | Engine developers and QA engineers verifying deterministic rendering. | Do not use to deduce production hardware topology or claim hardware verification. |
| [baselines/show-orchestration-v1/](baselines/show-orchestration-v1/) | `ACCEPTED BASELINE` | `ACCEPTED SOFTWARE EVIDENCE` | Machine-readable evidence (10 JSON/JSONL files) for 9,000-frame (300s @ 30 FPS) deterministic render digest (`53cf300d...`), offline-capacity metrics, protocol sequence trace, and bounded memory state. | Software acceptance evidence for Phase 17; software benchmark evidence. | Engine architects, benchmark reviewers, and regression runners. | Do not generalize simulator/memory benchmarks to RK3588 production hardware performance. |
| [baselines/phase34-branch-lifecycle/](baselines/phase34-branch-lifecycle/) | `ACCEPTED BASELINE` | `ACCEPTED SOFTWARE EVIDENCE` | Machine-readable benchmark evidence (`benchmark.json`) validating software capacity across 12 cases (5 hidden `pre_roll` branches on 9 strips / 200 pixel groups reach 161.9 FPS). | Software acceptance benchmark evidence for Phase 34 branch lifecycle and pre-roll execution. | Engine performance engineers and authoring tool developers. | Do not treat Windows development host CPU throughput as RK3588 hardware timing. |
| [baselines/cabin-lighting-v3/](baselines/cabin-lighting-v3/) | `ACCEPTED BASELINE` | `ACCEPTED SOFTWARE EVIDENCE` | Retained Phase 29 software acceptance evidence (`evidence.json` explicitly records `phase: phase-29-v3-e2e-acceptance`, 13 digital strips, 260 pixel groups, and 5 provisional ESP32 nodes, replay SHA `fe47009b...`, UDP v3 JSON SHA `1eecdd68...`). | Retained Phase 29 software acceptance evidence under a legacy directory name; subordinate to current production profile. | Maintenance engineers reproducing historical Phase 29 acceptance runs. | Do not use to infer Phase 31 one-ESP32-per-strip or current 9-ESP32 production topology (Phase 29 used 5 provisional nodes). |
| [runs/](runs/) | `LOCAL RUN OUTPUT` | `PROVENANCE REQUIRED BEFORE CLEANUP` | Working directory for local, uncommitted benchmark runs, profiling outputs, test artifacts, and possibly unique evidence or source. | Ignored by version control; inspect and archive unique materials before cleanup. | Local developers running benchmarks or tests. | Do not cite as accepted baseline evidence without review, or remove contents before rescuing unique material. |
