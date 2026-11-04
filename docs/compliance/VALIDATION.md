# Copyright audit — validation and change record

Date: 2026-10-26 (Asia/Singapore). Checkout HEAD: `fbaab17dd953b0c968fa00e11db941ffea775926`.

Copyright release result: **BLOCKED**, as documented in [OPEN_RISKS.md](OPEN_RISKS.md). Software regression result: **not all passing**. No firmware, RK3588 or hardware verification was performed: **NOT HARDWARE VERIFIED**.

## Actual commands and results

All Windows Python commands used `.\.python\Scripts\python.exe`. The interpreter check printed `PROJECT_PYTHON_OK`, with the interpreter resolving to the shared repository venv and `light_engine` resolving under this checkout; exit 0.

| Command (after the bundled interpreter prefix where applicable) | Return code | Actual outcome / elapsed time |
|---|---:|---|
| `git status --short`; `git rev-parse HEAD`; `git rev-parse --is-shallow-repository`; `git rev-list --all --count`; `git for-each-ref` | 0 | Dirty/staged user work recorded; 191 reachable commits; non-shallow local repository. |
| `git log --all`, path/diff/pickaxe filters; `git ls-tree`; `git cat-file`; `git reflog show --all` | 0 for successful evidence batches | Historical dependency/header/media discovery; WLED scope and limits recorded separately. |
| `git fsck --connectivity-only --no-reflogs` | 0 | No missing reachable object reported; dangling objects including 25 commit tips. This is not a full prior-development-history guarantee. |
| `-m pytest -q` before edits, restricted environment | 1 after interruption | Stalled after 41%; no pass count or total elapsed was emitted. Not a passing baseline. |
| `-m pytest -q --suite fast` before edits | 0 | **381 passed, 10.51 s**. Valid pre-change baseline for unchanged runtime behavior. |
| `-m pytest -q -o faulthandler_timeout=60`, restricted environment | 1 after interruption | Captured stack blocked in Windows `socketpair` / asyncio self-pipe / Starlette TestClient initialization. No final test count emitted. |
| `-m pytest -q tests/test_distribution_materials.py` before generator existed | 1 | **1 collection error, 1.21 s** (`ModuleNotFoundError`): observed test-first red state. |
| `-m pytest -q tests/test_distribution_materials.py` after worker implementation | 0 | **5 passed, 1 skipped, 1.80 s**. Earlier worker result before owner packaging correction. |
| `-m pytest -q tests/test_distribution_materials.py::test_copied_notices_are_not_excluded_by_environment_ignore_rules` before output-path fix | 1 | **1 failed, 3.36 s**; exact reproduction of license copies omitted by `.python/` ignore rule. |
| `-m pytest -q tests/test_distribution_materials.py tests/test_phase35_coherent_noise_field.py` after final tool change | 0 | **20 passed, 1 skipped, 4.36 s**. Simulated Windows reparse, unsafe RECORD and output-link coverage passed. Actual directory-symlink case skipped because this environment cannot create that symlink. |
| `scripts/compliance/generate_distribution_materials.py --root . --audit-date 2026-10-26` | 0 | Generated final local materials; explicitly prints **release_status=BLOCKED**. |
| `-m pytest -q --suite fast` final | 0 | **381 passed, 11.56 s**. Later generator-only packaging change does not alter fast-suite inputs. |
| `-m pytest -q -o faulthandler_timeout=60` with local communication permitted, first completed run | 1 | **1218 passed, 3 failed, 1 skipped, 83.30 s**, 3 deprecation warnings. Before one extra generator packaging test. |
| Same ordinary production command, final completed run | 1 | **1219 passed, 3 failed, 1 skipped, 82.37 s**, 3 deprecation warnings. No tests were removed or relaxed to change this result. |
| Owner Python SHA-256/input/copy/kiosk checks | 0 | All **171** captured source-input hashes match; all **69** copied-license hashes match; public and current-dist kiosk notices match byte-for-byte. `INPUT_LICENSE_KIOSK_EVIDENCE_OK`. |
| `git check-ignore` on original `.python` license-copy path | 0 | Confirmed omission risk. Corrected copies use `installed-python`; normal untracked-file discovery now sees all **69**. |
| `git diff --check` | 0 | No whitespace errors; Git emitted existing CRLF conversion warnings. |
| `git diff --stat`, `git diff --stat HEAD`, `git diff --cached --shortstat` | 0 | See change boundaries below. |

The three final ordinary-regression failures are:

1. `tests/test_host_service_api.py::test_ensure_mpv_stale_socket`: test expects `--vo=xv`, while the existing user-modified player command does not include it.
2. `tests/test_wled_nine_node_profiles.py::test_default_wled_profile_is_nine_independent_ddp_nodes_without_analog_placeholders`: expected historical pixel counts differ from current profile values.
3. `tests/test_wled_nine_node_profiles.py::test_ddp_and_udp_v3_maintenance_profiles_share_nine_strip_semantics`: current DDP strip lengths differ from maintenance-profile values.

This audit did not change those source/config/test files. They remain unresolved software verification results, separate from the copyright evidence blockers. The fast and focused checks do not override these failures.

No `--suite full`, benchmark, firmware build, upload, source publication, commit, push, stage or deployment was performed. This task changes audit tooling and notices, not runtime architecture/protocols or a firmware release; actual commercial release is blocked on external evidence.

## Generated evidence and identified gaps

Final inventory: **39** uv records (including platform/Python alternatives), **77** npm records, **39** local distributions, **69** copied license files, **18** apt installer requests, **9** current media entries, **5** historical media objects, **171** hashed source inputs, **0** inventory warnings. Zero warnings means capture completed within its recorded scope; it is not a legal pass.

Local `pyserial` lacks a copied license file in its installed metadata; its exact upstream 3.5 BSD original is separately retained under `licenses/pyserial-3.5-BSD-3-Clause.txt`. `light-engine` has no grant recorded in installed metadata. The actual copyright owner/customer license remains R6. The local FastAPI version 0.141.1 differs from locked 0.139.2; this is further evidence that this venv is not the final image SBOM.

Primary-source retrieval used public official URLs through Firecrawl. Successful license/source retrievals returned HTTP 200; the initially attempted GNU GCC exception `.txt` URL returned 404 and was replaced by the pinned GCC repository's `COPYING.RUNTIME`. Text-extraction identities, rather than unverified raw Git bytes, are labeled in source records. No private repository source or media was uploaded. The WLED worker's denied socket download, initial tool-schema error and successful fallback are recorded in WLED_PROVENANCE.md.

## Modified files and ownership

Existing tracked source modified by this audit: **only** `light_engine/effects/coherent_noise.py`, a comment-only change (**5 insertions, 4 deletions**) identifying the public-domain SplitMix64 finalizer. The worker independently compared code with comment lines removed and found no executable difference from audit HEAD.

New authored/prepared files:

- `THIRD_PARTY_NOTICES.md` and `SOURCE_AVAILABILITY.md`.
- `scripts/compliance/generate_distribution_materials.py` and `tests/test_distribution_materials.py`.
- `kiosk/public/THIRD_PARTY_NOTICES.txt`; an identical file is present in current ignored `kiosk/dist/THIRD_PARTY_NOTICES.txt` without rebuilding JavaScript. Existing JS/CSS/HTML are unchanged.
- `docs/compliance/`: plan, open risks, target-evidence guide, WLED comparison, this validation record, governance note, source indexes, original license texts, generated inventory/notices/license copies and artifact identity manifest.

All pre-existing dirty/staged files were preserved. `git diff --cached --shortstat` remains **81 files changed, 856 insertions(+), 348 deletions(-)**, the same staged summary recorded at the start. Newly authored files are intentionally unstaged. The full working-tree `git diff --stat` below includes the user's pre-existing unstaged changes and excludes all untracked audit files:

```text
 AGENTS.md                                 | 11 ++++-
 docs/current/rk3588-bootstrap.md          | 64 ++++++++++++++++++++++++++---
 host_services/engine_adapter.py           |  3 +-
 light_engine/effects/coherent_noise.py    |  9 +++--
 scripts/deploy/rk3588/bootstrap.sh        | 22 +++++-----
 scripts/deploy/rk3588/install-services.sh | 31 ++++++++++++--
 scripts/deploy/rk3588/setup-system.sh     |  4 +-
 scripts/deploy/rk3588/verify-install.sh   | 67 ++++++++++++++++++++++++++++++-
 tests/test_host_service_api.py            | 17 ++++++++
 9 files changed, 202 insertions(+), 26 deletions(-)
```

`git diff --stat HEAD` (all pre-existing tracked work plus the single audit comment change): **84 files changed, 1038 insertions(+), 354 deletions(-)**. New audit artifacts are enumerated separately in `evidence/artifact-manifest.json`; their hashes document this audit snapshot, not permanent source freezes or fixed-hash tests.

The obsolete generated `.python` notice directory was created during this task. Before removing it, the owner checked its exact resolved absolute path under `docs/compliance/generated/LICENSES/`, rejected reparse points, and verified its expected 69-file count. No user media, cache, environment or prior file was removed.

## Delegation and review evidence

Used direct, non-overlapping read-only workstreams: `engineer` / GPT-6.1 Sol high for WLED history/expression analysis; `worker` / GPT-6 Luna high for runtime dependencies; `worker` / GPT-6 Luna high for firmware/media. Reused runtime worker for its bounded inventory tool. Independent `reviewer` / GPT-6.1 Sol high checked license boundaries, source-offer status and generated identities; no supervisor was needed. Agent elapsed/usage were not measured, so no cost-optimum claim is made.

Review led to two supported document corrections: add certifi/MPL covered-file obligations; condition WLED source duties on actual version/dependency terms. Source-providing requirements and unresolved target facts remain explicit. No whole-application open-source grant was added.
