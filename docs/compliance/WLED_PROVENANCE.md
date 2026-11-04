# WLED and effect-code provenance audit

Audit date: 2026-10-26. Audited checkout HEAD:
`fbaab17dd953b0c968fa00e11db941ffea775926`.
This document records a bounded source comparison, not a copyright clearance.
Current uncommitted user work was preserved. No test suite, Python, firmware,
or hardware command was run by this audit worker.

## Findings

The inspected native effects contain material implementation differences from
the compared WLED functions. The available evidence does **not** establish that
all code was independently authored, nor that no WLED expression was copied.
The repository's clean-room declarations are assertions being checked, not
evidence that independently proves that process.

One definite expression-level correspondence exists outside the WLED-specific
comparison: `light_engine/effects/coherent_noise.py:31-35` in the current
working tree (lines 30-34 at the audited HEAD) uses the published
SplitMix64 finalizer. Its primary author source expressly dedicates rights to
the public domain to the extent possible and grants unconditional permission.
The owner has corrected the former own-origin wording at historical lines
23-24; the current attribution occupies lines 23-27. That later comment
correction is a remedy, not additional proof about the earlier source. This
finding does not establish a WLED/EUPL dependency or a need to replace the algorithm.

The structured evidence, exact screen definitions, source retrieval identifiers,
extraction hashes, per-file version counts, and limitations are in
[evidence/wled-comparison.json](evidence/wled-comparison.json).
The complete small primary SplitMix source, including its permission statement,
is preserved at
[evidence/splitmix64-source.txt](evidence/splitmix64-source.txt).

## What history was checked

The local graph has **191 reachable commits**, **74 refs**, and two roots.
`git rev-parse --is-shallow-repository` returned `false`; no replace refs or
partial-clone/promisor configuration was observed. `git fsck
--connectivity-only --no-reflogs` returned 0 and reported dangling objects,
including **25 dangling commit tips**. Their metadata was inspected, with dates
from 2026-07-05 through 2026-08-20; most are WIP/preservation stashes, and one
is a Phase 9 firmware commit. No Phase 32-40 named dangling tip was observed.
Their trees were not recursively audited.

All locally reachable versions under `light_engine/effects/*.py` and
`light_engine/analysis/wled_audio_sync.py`, including nested copies in the
stash root, yielded **101 unique Git blobs across 27 file basenames**.
Thirteen commits touch the main effect directory.

| Earliest reachable introduction | Files or scope | Provenance limit |
| --- | --- | --- |
| `f56db3dbdc7bb9907bf91c36d1d300b883c66232`, 2026-07-04 | Fourteen initial effect source files, including breath, chase, comet, color_wave | Already present in the root baseline snapshot; earlier authorship is unavailable. |
| `80ded3a3aa6ffa771d74ebedab0d24c1f510bfab`, 2026-07-13 | color_wipe, twinkle | First reachable introduction, not proof of original authorship. |
| `70ca1009f3d4427179ebdc7f2d5f62794c065734`, 2026-07-17 | single_dot, step_pulse, theater_phase | Same limit. |
| `0962d74e7b29f0874843a8b4870933308ee0bbb7`, 2026-08-22 | flowing_bands, heat_fire, onset_ripple, history_stream, scalar_source, Audio Sync | Aggregate Phase 32-34 commit; incremental research/authoring steps are absent. |
| `06ae1220d296942029c61f9d9ca61a638db27d51`, 2026-08-23 | coherent_noise, coherent_noise_field | Aggregate Phase 35-40 commit; same limit. |

The other root, `60bd965a303f8d2a6357d2fcf94499387a4b8110`, is an
untracked-files stash snapshot containing nested baseline source copies.
Reachability and connectivity do not prove that all former remote branches,
uncommitted development, or deleted history are present. No network fetch or
remote-history refresh was performed.

No deletion of copyright/license header text was observed in the reachable
effect diffs searched with the word-bounded keywords specified in the JSON.
That does not exclude removal before the first baseline snapshot or notices
that use different wording.

## Structured source comparison

The principal reference is WLED **v16.0.1**, commit
[`29b389df1c1aaec6ff53aea742d17063b985906c`](https://github.com/wled/WLED/commit/29b389df1c1aaec6ff53aea742d17063b985906c).
The official [release page](https://github.com/wled/WLED/releases/tag/v16.0.1)
links that commit. Full text extractions were obtained from the pinned
[FX.cpp](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp)
and [audio_reactive.cpp](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp).
The older [v0.14.4 FX.cpp](https://github.com/wled/WLED/blob/v0.14.4/wled00/FX.cpp)
was compared separately; its tag was not resolved to an immutable full commit
during this audit.

The source-line numbers below use those full text extractions, not the web
tool's compacted display numbering. GitHub reports 11,224 lines for the pinned
FX.cpp, matching the extraction's newline count.

| Local evidence | Compared WLED function | Observation and interpretation |
| --- | --- | --- |
| `heat_fire.py:64-126` | `mode_fire_2012`, FX.cpp:2157 onward | Shared cooling/transport/ignition idea. Local float interpolation, SHA-derived per-tick RNG, 60 Hz replay, and RGB-times-heat rendering differ from the inspected upstream stencil, timing, state, and palette expressions. |
| `flowing_bands.py:83-106` | `running_base`, FX.cpp:594 onward | Local fixed mask selects one discrete highlighted band; compared upstream samples a moving waveform. This is a mechanism difference, not just different identifiers. |
| `onset_ripple.py:64-83,195-257` | `mode_ripplepeak`, FX.cpp:6651 onward; `ripple_base` | Both can react to peaks and have a 16-wave/ripple bound. Local timestamped events, triangular spatial shape and exponential decay differ from the compared state machine. The shared bound is weak evidence by itself. |
| `breath.py:49-57` and root version | `mode_breath`, FX.cpp:432 onward; older counterpart | Ordinary sine envelope differs from upstream folded integer counter. Earlier source origin remains unavailable. |
| `twinkle.py:236-288` | `mode_twinkle`, FX.cpp:655 onward; older counterpart | Local density/time spawn accumulation and retained-color decay differ from inspected seeded incremental selection. |
| `coherent_noise.py:20-70` current; 20-69 at audited HEAD | `mode_noise16_1/2`, FX.cpp:2237 onward | Local hashed lattice value noise and four-corner interpolation differ from the compared Perlin/palette recipe. Quintic interpolation alone is a common mathematical mechanism. |
| `analysis/wled_audio_sync.py:22-27,49-80` | `audioSyncPacket`, audio_reactive.cpp:800-812, header at 2320 | Matching wire layout/constants are needed for interoperability. The local Python decoder has its own validation and generic feature normalization; wire agreement is not matching renderer expression. |

These are selected expression/state comparisons, not an exhaustive semantic
clone detector. Earlier chase/comet implementations and later versions were
also inspected through their local history. Common effect names, modulo
masks, sine waves, fading, or numeric output differences alone do not establish
or refute copying.

A mechanical supplemental screen found **zero shared six-word comment
phrases** among **56 distinct eligible Python # comment lines** from the 101
local blobs and the three full upstream extractions. The JSON records exact
normalization and exclusions. This screen excludes docstrings, renamed or
translated code, wrapped comments, and other upstream files/versions. A zero
result is not clearance.

## Definite SplitMix correspondence

At current `coherent_noise.py:31-35` (historical lines 30-34 in the audited
HEAD and introduction commit `06ae1220d296942029c61f9d9ca61a638db27d51`),
all five mixer operations match the primary
[SplitMix source](https://prng.di.unimi.it/splitmix64.c), which redirects to
[splitmix.c](https://prng.di.unimi.it/splitmix.c):

1. XOR right shift by 30.
2. Multiply by `0xBF58476D1CE4E5B9` modulo 2^64.
3. XOR right shift by 27.
4. Multiply by `0x94D049BB133111EB` modulo 2^64.
5. XOR right shift by 31.

The local pre-mixing of coordinates and final float normalization are different.
The distinctive sequence is stronger evidence than a shared algorithm name.
It identifies the published mixer expression, but cannot identify which source
the implementer actually consulted. The 2015 primary source credits Sebastiano
Vigna and includes public-domain dedication plus unconditional permission;
its full header is preserved in the evidence file. No attribution condition
appears in that header. Recording provenance is the supported correction;
this finding does not create a demonstrated copyleft obligation.

The other two local coordinate pre-mix constants are recorded in the JSON but
their ultimate origin has not been established. No copying conclusion is
inferred from those constants alone.

The compared WLED FX headers identify Harm Aldick / WS2812FX ancestry; Fire2012
credits Mark Kriegsman. Those are upstream provenance leads. They do not,
without matching local expression, establish that LIGHT-BELT copied WS2812FX,
FastLED, or Fire2012 source.

## License facts and minimum next steps

The pinned WLED
[LICENSE](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/LICENSE)
states EUPL v1.2 or later. The older
[v0.14.4 LICENSE](https://github.com/wled/WLED/blob/v0.14.4/LICENSE)
and its FX header use MIT. The complete older root license is preserved at
[licenses/WLED-v0.14.4-MIT.txt](licenses/WLED-v0.14.4-MIT.txt), including its
copyright, permission, notice-retention condition and warranty terms.
The actual delivered controller firmware version remains unknown: the EUPL
conclusion applies to the pinned modern WLED version, while an actual older
MIT build must be assessed against its own source, modifications and dependency
licenses. An old permissive version is not automatic permission to use later
expressions or to ignore third-party notices.

The saved modern [license](licenses/WLED-EUPL-1.2.txt) was checked against a
fresh text extraction from the pinned modern commit URL. The content matches
with one added final LF in the saved file: extraction SHA-256
`3154727a66bfa8a3ece1be140cde998746d8501b47d6d63a7f4f6d248009a18b`;
saved-file SHA-256
`5d502840a45abb28b2d7f14239bb8f62934ed1a3923ce2e810c5c6c0958ac086`.
These are extraction/artifact hashes, not independently verified upstream Git
blob IDs. The older license's URL, extraction and saved-file hashes are also
recorded in the JSON source index.

Supported minimum actions are:

- Keep the corrected SplitMix attribution and the primary source/permission
  evidence. The owner completed the comment-only correction; preserve the algorithm.
- Retain precise source-version and provenance records. Do not present the
  repository's clean-room assertion or this audit's negative screens as proof.
- Before shipping WLED controllers/firmware, identify the actual delivered
  firmware/image, modifications and licenses/notices; provide source and build
  materials to the extent required by that actual version and its dependencies.
  MIT itself requires its notices, not a blanket source offer. Modern EUPL
  versions require the applicable source-access route. Device shipment is
  a separate concrete distribution question even if the Host effects were
  independently written.

This audit does not establish an obligation to relicense the complete Host
application merely because it communicates with, or is delivered beside, WLED.
A derivative/combined-work decision needs the actual source, packaging,
distribution and applicable-law facts. The actual shipped firmware build,
complete dependency notices, and pre-baseline authorship remain unresolved.

## Evidence and validation

The owner supplied a valid pre-change fast baseline: 381 passed in 10.51 s,
exit 0. This worker did not rerun suites. Its changes are confined to this
document, its two comparison evidence files, and the added older MIT license.
The modern license file was verified without modification. No suite was run
for the follow-up source-index and line-reference corrections.

Read-only commands included `git status --short`, `git rev-list --all
--count`, `git for-each-ref`, `git log --all` with path/pickaxe/diff
filters, `git ls-tree`, `git cat-file blob`, `git reflog show --all`,
`git fsck --connectivity-only --no-reflogs`, `rg`, and Node scripts that
enumerated and screened local blobs. Successful command batches returned 0.
No repository source was uploaded; connector requests contained only public
upstream URLs and retrieval objectives.

Shell `Invoke-WebRequest` to the public raw URL failed because socket access
was denied; its containing batch later returned 0, so that batch code is not
evidence of successful retrieval. Firecrawl returned HTTP 200 for the four
full-source extractions. A first Firecrawl call lacked its required
`objective` argument and failed validation; the corrected calls succeeded.
The web tool could not fetch the SplitMix URL directly or the GitHub tag API;
the public connector retrieved the primary SplitMix source instead.

The JSON hashes identify UTF-8 encodings of the retrieved text fields, **not
verified original HTTP response bytes or upstream Git blob IDs**. Full large
WLED source files are not copied into tracked documentation; the pinned URLs,
retrieval IDs, extraction hashes and selected comparison evidence are retained.

