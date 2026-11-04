# Commercial copyright audit — 2026-10-26

**Goal:** prepare evidence and distribution notices for sale of LIGHT-BELT hardware while preserving proprietary rights wherever the actual licenses permit it.

**Authorized scope:** the user's seven audit requirements in this chat, including audit before modification, minimum confirmed remedies, no architecture changes, no proactive publication of proprietary code. This is a separate compliance task, not Phase 41. No commit, stage, push, hardware access or deployment is authorized.

## Evidence and execution ledger

- [x] Record existing dirty/staged changes; preserve them. Starting HEAD: `fbaab17dd953b0c968fa00e11db941ffea775926`.
- [x] Verify bundled interpreter: `PROJECT_PYTHON_OK`, exit 0.
- [x] Read authority documents, manifests, current distribution paths and relevant Git history before editing.
- [x] Delegate independent read-only WLED/history, runtime/front-end/player, firmware/media investigations.
- [x] Establish pre-change baseline: `pytest -q --suite fast`: 381 passed, 10.51 s, exit 0. Earlier ordinary production run stalled after 41% and was interrupted, exit 1; it is not a passing baseline.
- [x] Obtain user distribution scope: device/system/controllers/demo media included; controller model/version, seller and sales territories unknown. No authorization to publish proprietary source was inferred.
- [x] Generate dependency, copyright, license, media and Git evidence inventories with exact input identities and explicit unknowns.
- [x] Add required original license/notice texts for known components; provide front-end copies in both current dist and Vite public inputs without rebuilding application code.
- [x] Record source-delivery requirements as preparation instructions, not a fictitious operational offer.
- [x] Independently challenge licensing boundaries, notice completeness and unsupported clearance claims. Added MPL-covered-file treatment and conditional old-MIT/new-EUPL wording after primary-source verification.
- [x] Execute focused generator tests, fast suite and ordinary production suite; retain failures/timeouts as limitations. Final outcomes are in VALIDATION.md. Execution does not mean every check passed.

## Observations before edits

1. No tracked LICENSE/COPYING/NOTICE bundle; README ends with `License: proprietary, internal use.` This statement alone establishes neither ownership nor customer commercial-use rights.
2. Local wheels contain third-party native libraries, including libsndfile, FFmpeg, OpenBLAS and GCC runtime exception text. Windows installation is evidence of development contents, not an RK3588 release SBOM.
3. Vue 3.5.40 is embedded in the tracked kiosk dist; short MIT license markers remain, but a full notice/permission text is missing from distribution inputs.
4. Actual WLED/GLEDOPTO firmware identity, vendor modifications and corresponding source cannot be confirmed. Firmware source trees in this repository are not proof of installed firmware.
5. `assets/energy-wakeup/energy-wakeup.mp4` exists outside Git and has no evidenced redistribution rights. Synthetic test-fixture provenance is separately documented.
6. WLED-related algorithm ideas and interoperability facts do not establish copied expression. Squashed commits and unreachable history limit a clean-room conclusion; direct comparisons remain necessary.

## Write ownership and acceptance

- Owner: this plan, audit findings, primary-source license snapshots/index, distribution/source instructions and kiosk notices. No existing functional source file or existing user edits are changed.
- Runtime inventory worker: only `scripts/compliance/generate_distribution_materials.py` and `tests/test_distribution_materials.py`; generated output under `docs/compliance/generated/` after owner review.
- WLED investigator: bounded provenance evidence under `docs/compliance/` only when explicitly released for writing by owner.
- Acceptance: artifacts clearly distinguish detected, declared, unverified and release-blocking facts. Unknown licenses/source/rights never become a pass. No whole-project relicensing or assertion of legal clearance follows from a test result.

## Review focus

- Wrongly treating a permissive Python wrapper as the license of native libraries.
- Treating a generic upstream link as fulfillment of GPL/LGPL corresponding-source requirements.
- Treating Windows dependency metadata as proof of ARM/system-image contents.
- Mistaking common effects/protocol facts or negative similarity searches for proof of independent authorship.
- Silently including unlicensed ignored media, proprietary history, or source secrets in the deliverable.

## Implementation choice

Use a small offline inventory generator and document-only remediation. It reads lockfiles and locally installed metadata; it never downloads, installs, contacts hardware, or publishes source. Original upstream texts are retrieved separately from public primary sources. Changes remain independently reviewable beside the user's existing work.

Final owner checks caught a packaging defect in the new generator: license copies under `.python` were ignored by the existing Git rules. A fixture reproducing those actual ignore rules first failed, then passed after moving output to `LICENSES/installed-python/`. All 69 copied notices are now visible to normal repository packaging. Obsolete copies created by this audit were removed only after checking their exact absolute output path, non-reparse status and expected 69-file count.

No existing runtime behavior, media, dependency selection, architecture or user staging was changed. The only existing source edit corrects SplitMix64 provenance in a comment. No Phase 41 work was started. Copyright release clearance remains BLOCKED by the recorded external facts.
