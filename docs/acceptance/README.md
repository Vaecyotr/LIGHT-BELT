# Software Acceptance Records

This directory contains human-readable software acceptance reports for completed project phases and verification campaigns.

## Acceptance Evidence Chain

For acceptance campaigns that use fixed fixtures and committed machine-readable baselines, the full three-tier evidence chain applies:

```
[config/acceptance/] (Fixed, immutable acceptance inputs & test fixtures)
       │
       ▼
[artifacts/baselines/] (Committed, machine-readable JSON/JSONL digests & metrics)
       │
       ▼
[docs/acceptance/] (Human-readable acceptance reports, traceability matrices, scope boundaries)
```

Where applicable, machine-readable counterpart baselines live under [artifacts/baselines/](../../artifacts/README.md) and static fixtures under [config/acceptance/](../../config/acceptance/README.md).
For other development phases, software acceptance may instead rely on focused test suites, source-level contract evidence, and a human-readable acceptance report in this directory. The absence of a dedicated artifact baseline does not mean a phase lacked formal software acceptance.

## Governance & Interpretation Rules

1. **Declared Scope Only**: Each acceptance report proves only the specific software features, contract boundaries, and assertions explicitly documented in its text.
2. **No Retroactive Topology Authority**: An older phase acceptance report (such as Phase 29 or Phase 31 reports) reflects the system state at that phase's completion; it does not override subsequent production profiles or the canonical authority defined in [CLAUDE.md](../../CLAUDE.md) and [config/profiles/rk3588-host-service.yaml](../../config/profiles/rk3588-host-service.yaml).
3. **Software Acceptance ≠ Hardware Verification**: Software acceptance demonstrates code correctness, protocol serialization, and offline engine performance under simulated environments. All physical installation, Wi-Fi networking, and electrical timing claims remain **`NOT HARDWARE VERIFIED`** unless supported by real physical measurements and completed checklists.
