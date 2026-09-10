# Show Test and CLI Compatibility Fixtures

This directory contains fixtures for tests and explicit CLI validation.
Production Host discovery remains under `assets/`, including the immutable
`assets/energy-wakeup/energy-wakeup.yaml`; do not edit its content.
Nothing in this directory changes that discovery or selects a production Show.
Retired fixtures are classified under `config/shows/archive/`.

`config/shows/energy-wakeup.yaml` is the only current Show compatibility
baseline, used only for tests and CLI validation. It need not be identical to
the production original. Files under `config/shows/archive/` are legacy regression material
and must not be used to infer current visual, parameter, topology, or authoring
requirements.

## Adding a compatibility fixture

Every new YAML must start with this comment header because the current loader
rejects unknown schema keys:

```yaml
# created_at: YYYY-MM-DD
# purpose: one sentence describing the intended experience or operation
# status: draft | approved
# source: assets/energy-wakeup/energy-wakeup.yaml | independent
# hardware_verified: false
```

Rules:

1. Use a descriptive, purpose-based filename. Do not encode obsolete campaign,
   node, GPIO, transport, or test names into a current Show filename.
2. Use only current target IDs, effects, and Show schema. Physical topology
   remains in profiles and mapping, never in the Show.
3. Treat `config/shows/energy-wakeup.yaml` and current runtime code as the
   compatibility boundary. Its immutable source is retained at
   `assets/energy-wakeup/energy-wakeup.yaml`; do not copy decisions from the
   32 legacy Shows or their archives.
4. Validate the file with the bundled interpreter and add only the focused
   tests needed by its new behavior.
5. Set `status: approved` only after explicit review; this does not make a
   fixture a production Show. Set
   `hardware_verified: true` only with real hardware evidence.
6. Archive retired Shows under `config/shows/archive/<category>/`. Keep the
   archive categories stable and preserve retired YAML bytes exactly.

Other diagnostic and regression fixtures belong in dedicated test/acceptance
or archive locations, not alongside the current compatibility baseline.
