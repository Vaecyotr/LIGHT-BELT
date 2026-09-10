# Test layers

The default is current production regression. `suites.json` records each file's
purpose and tier; a Phase number in a filename does not determine its layer.
Use the repository bundled interpreter on Windows.

| When | Command | Coverage |
| --- | --- | --- |
| Daily development | Relevant explicit test paths, then `.\.python\Scripts\python.exe -m pytest -q --suite fast` | Small model, color, configuration, effect, timeline and composition contracts |
| Ordinary task completion | `.\.python\Scripts\python.exe -m pytest -q` | Fast plus current production integration, Host/API, DDP, analysis, mapping, Show/effect behavior and output safety |
| Large/cross-layer changes or pre-release | `.\.python\Scripts\python.exe -m pytest -q --suite full` | All tests, including maintenance, tooling, firmware-related software checks and history |
| Historical investigation alone | `.\.python\Scripts\python.exe -m pytest -q --suite history` | Frozen Phase/campaign artifacts and retired deployment Show replay |

`--suite production` explicitly selects the default. These are not four disjoint
sets: fast is part of production; full includes all three other layers. A full
run therefore also checks history. No xfail/skip is used to hide historical failures.

Explicit paths/node IDs, such as `pytest tests/test_udp_v3.py -q`, run those
requested tests without layer filtering. An explicit `--suite` filters an explicit
path too. `pytest tests -q` consequently means all tests; bare `pytest -q` is production.

New/unclassified test files stay in production and full. Add their purpose and
tier to `suites.json` during review. Invalid tiers fail collection. DDP adoption
does not retire UDP or RS-485; protocol safety coverage remains in full.

## Counts and timing

Complete Windows bundled-Python runs on 2026-09-10:

| Layer | Passed | Pytest elapsed | Exit code |
| --- | ---: | ---: | ---: |
| fast | 381 | 3.11 s | 0 |
| production | 1192 | 33.75 s | 0 |
| full | 1495 | 254.05 s | 0 |
| history | 115 | 190.24 s | 0 |

The final counts, measured timings, slowest tests/files, exact commands and
limitations are recorded in [the audit](../docs/testing-audit.md).
Append `--durations=25 --inventory-json=tmp/test-audit/<run>.json` to a real run
for individual durations and per-file inventory. Use `--collect-only` only when
counting; it does not validate tests and reports `null` for unmeasured time.

Counts include parameterized cases. File seconds sum setup, call and teardown;
shared-fixture setup is charged to the first consuming test. This is not an
isolated file benchmark. The pytest total includes collection and other overhead
and is reported separately. Raw reports/logs live under ignored `tmp/test-audit/`.

The 2026-09-09 partial audit and waived full run are historical context only;
the 2026-09-10 closeout uses complete actual runs and does not inherit that waiver.

## File changes, SHA and historical evidence

Use **behavior tests for correctness, Git/review for file changes, and SHA for
release/firmware/protocol or deliberately byte-locked fixture identity**.
Ordinary evolving Show/YAML/source files must not gain fixed SHA gates.
Temporary cleanup hashes are removed once the cleanup is reviewed.

- The two temporary Show freezes were removed. The three long-term provenance
  comparison cases now live in `test_campaign_evidence_comparison.py` (full).
  Only top-level `generated_from_head` may differ; rendered values and nested
  provenance remain compared, and current generation must identify Git HEAD.
- Phase 32's two obsolete current-Show freeze tests were retired to
  [historical documentation](../docs/history/phase32-energy-wakeup-freeze.md).
  Their old hashes were preserved, not regenerated. Past acceptance command logs
  remain historical records, not runnable current instructions.
- The Host discovers Shows under `assets/`. `config/shows/energy-wakeup.yaml`
  is an independent test / CLI compatibility fixture. No current source==fixture
  relationship is imposed. Tests retain config-fixture loading/target validation
  and generic Host discovery using temporary asset directories; they do not
  certify the actual production assets file against the current deployment.
- Historical fixed render hashes stay in history. Protocol Golden Vector identity,
  locked audio input identity, generated artifact manifest consistency and dynamic
  two-run determinism are retained for their distinct purposes; see the audit inventory.

## Bounded cleanup decisions

Ten-second real-time Engine acceptance, 300-second simulated music history pressure
and throughput measurement live in full. Production retains short stop/duration/frame
contracts, music expectations/determinism and a capacity-boundary check. Current
Host/API integration stays in production despite its cumulative runtime.

Single-strip generation is shared across campaign/observability tests; a second
independent generation still verifies determinism. Copy-suffixed campaign modules
and possible UDP/serial overlaps retain unique assertions and were not deleted
without a coverage mapping. `test_pipeline.py` was removed in the preceding cleanup
with its unconsumed scaffold; real complete-frame queue coverage remains in
`test_output_safety.py`.

Software tests do not imply firmware builds or physical acceptance.
**NOT HARDWARE VERIFIED**.
