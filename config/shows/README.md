# Active Show Admission Rules

This directory contains the approved, runnable current Show copy. The immutable
original source for the current copy is
`assets/energy-wakeup/energy-wakeup.yaml`; do not edit or run that source as
the current Show. Retired Shows are classified under
`config/shows/archive/`; they are not current references. Any future current
Show must be intentionally approved under the rules below.

`config/shows/energy-wakeup.yaml` is the only current Show compatibility
baseline. Files under `config/shows/archive/` are legacy regression material
and must not be used to infer current visual, parameter, topology, or authoring
requirements.

## Adding a Show

Every new YAML must start with this comment header because the current loader
rejects unknown schema keys:

```yaml
# created_at: YYYY-MM-DD
# purpose: one sentence describing the intended experience or operation
# status: draft | approved | production
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
5. Set `status: approved` or `production` only after explicit review. Set
   `hardware_verified: true` only with real hardware evidence.
6. Archive retired Shows under `config/shows/archive/<category>/`. Keep the
   archive categories stable and preserve retired YAML bytes exactly.

Diagnostic and regression fixtures belong in dedicated test/acceptance or
archive locations, not in this active directory.
