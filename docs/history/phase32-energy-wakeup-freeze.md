# Historical Phase 32 Energy Wakeup freeze

These values are a historical record, not an executable contract for current Shows.
The retired test read `assets/energy-wakeup/energy-wakeup.yaml` and
`config/shows/energy-wakeup.yaml`, required byte SHA identity for the former,
YAML/load equality between both, and the following representative render hashes.
The current Host discovers Shows under `assets/`; the config Show is an independent
test / CLI compatibility fixture. Those old equality assumptions no longer apply.

The two tests from `tests/test_phase32_energy_wakeup_non_regression.py` were
removed during the 2026-09-10 cleanup. No historical digest was refreshed.
Config-fixture loading/target validation, effect behavior and generic Host discovery
remain tested. This does not certify the actual production assets file against
the current deployment.
Past acceptance reports retain their original command/result records.

Historical asset SHA-256: `627d23a4c73e66f1913c7b5cbb15cf1b16926e6772289237165535a2278c142d`

| Timestamp (s) | Historical render SHA-256 |
| ---: | --- |
| 1.0 | `b8fdd0f03e6df638ec278df18bcebf2d5de95cefe5d59929c252917a199b7858` |
| 28.0 | `8f893a00f0da295708820a05517a20c716c104dd8354cee8231b5a1bc0cafedb` |
| 75.0 | `ef04adab6b721be3d221e11b4090feffe010cd3e723e1cd3543d9b05ba6fe61f` |
| 150.0 | `99dabd601ebc7759f1b13d3c602d00c3fc43278e4d48ab4f25eda26ccec29bec` |
| 225.0 | `fc59465b8b5f310cf038add5667627ec67a605a44b93faded75a7d63f1608450` |
| 300.0 | `77ca71ff43e4f2c7dba800ed637b62262654212265c723f685c2e8ca707159dc` |

Render identity used seed 0, a fresh runtime per timestamp, sequence 1 through 6,
delta time 1/30 s, the then-current host-service profile, and SHA-256 of sorted,
compact JSON containing strip/zone IDs and channels rounded to nine decimals.
These are historical identities, not desired current output values.

**NOT HARDWARE VERIFIED**.
