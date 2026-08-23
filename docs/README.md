# Documentation Index

This index is the master entry point for repository documentation.
Directory lifecycle categorizes document roles, but per-file README classification determines each document's precise authority and scope; a retained document in `current/` may contain explicitly historical or maintenance-only sections.

## Authority

When documents or code disagree, resolve conflicts in this exact order:

1. [CLAUDE.md](../CLAUDE.md) — permanent project facts and architecture invariants.
2. [CLOSED_LOOP_SPEC.md](CLOSED_LOOP_SPEC.md) — target behavior and protocol contracts.
3. [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — currently approved work and closure evidence.
4. Current source implementation and focused tests — evidence of implemented behavior.
5. Directory-level navigation indices and individual document status declarations.

## Navigation by Role

- **[Current Operations, Authoring & Maintenance (`docs/current/`)](current/README.md)**:
  Active operational runbooks, authoring guides, Host Service deployment, and retained maintenance procedures.
  - *Show Authoring Entry Point*: [show-authoring-source-index.md](current/show-authoring-source-index.md)
  - *Canonical Authoring Guide*: [show-v2-authoring.md](current/show-v2-authoring.md)
  - *Host Deployment*: [host-service-deployment.md](current/host-service-deployment.md)

- **[Technical Reference & API Contracts (`docs/reference/`)](reference/README.md)**:
  Normative API contracts, effect metadata, wire protocols, and research closure records.
  - *Frozen External APP Facade*: [host-api-v1.md](reference/host-api-v1.md) & [host-api-v1.openapi.yaml](reference/host-api-v1.openapi.yaml)
  - *Native Effect Reference*: [effect-reference.md](reference/effect-reference.md)
  - *Internal Parameter Metadata*: [effect-parameter-metadata.md](reference/effect-parameter-metadata.md)
  - *Parameter Modulation*: [parameter-modulation.md](reference/parameter-modulation.md)
  - *Dynamic ColorSource*: [color-source.md](reference/color-source.md)

- **[Software Acceptance Records (`docs/acceptance/`)](acceptance/README.md)**:
  Human-readable acceptance reports summarizing verified software evidence for completed phases.
  - *Acceptance Evidence Chain*: [docs/acceptance/README.md](acceptance/README.md)
  - *Machine-Readable Counterparts*: [artifacts/README.md](../artifacts/README.md)
  - *Test Fixtures*: [config/acceptance/README.md](../config/acceptance/README.md)

- **[Historical Archives (`docs/history/`)](history/README.md)**:
  Preserved historical plans, early prototype notes, and completed campaign artifacts retained strictly for provenance.

## Governance & Verification Boundaries

Software acceptance demonstrates deterministic simulation correctness and offline capacity; it does not prove physical hardware installation. All electrical timing, multi-node Wi-Fi synchronization, and field deployment claims remain **`NOT HARDWARE VERIFIED`** until verified with physical hardware measurements.

See [Repository Governance](repository-governance.md) for full lifecycle management rules.
