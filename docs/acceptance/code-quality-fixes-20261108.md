# Code quality remediation acceptance

## Baseline and scope

The pre-remediation baseline is commit
`3841e88aa0334cf1d5b16b4ad73970a1f1a60812`. It preserves all 27 previously
changed tracked/untracked paths, including the deleted Kiosk asset. The `1108`
publication branch contains this baseline followed by the quality repairs.

The approved repair scope covers Q01, Q02, Q03, Q04 and Q07, followed by the
combined state collection, sending and lifecycle work in Q05, Q06 and Q10.
Q14 test-output isolation was also corrected when completing regression checks.

## Maintained contracts

| Finding | Result | Regression evidence |
| --- | --- | --- |
| Q01 | Safely unlink the shared Python entry before asking Git to remove a worktree. Git rejection or an unexpected remaining directory raises an error. Recursive worktree deletion is removed. | Dirty, locked and unknown Git failures with and without force, shared-target preservation, unexpected residual directory. |
| Q02 | PulseAudio stream ownership uses the supported `pacmd update-sink-input-proplist` command with values `1` and `0`. CLI diagnostics count as failure even with exit code zero. Ownership is read from the server stream. | Adapter command/error contract, externally muted stream, restart recovery, reused stream index. |
| Q03 | `pactl`, `pacmd` and subscription subprocesses inherit the environment with `LC_ALL=C`. | Query, update and subscription environment assertions. |
| Q04 | Scene creation, replacement and deletion publish memory only after atomic file replacement. Errors return HTTP 500. Failed temporary writes are cleaned up. | Public API failures at open/replace for all three operations, unchanged memory/disk/selection, successful reload. |
| Q07 | Engine initializes live audio and outputs inside its cleanup boundary, then calls the readiness callback before rendering. CLI initialization/run diagnostics remain distinct. | Real Engine preparation with live-audio/output failure, no early READY, single open and cleanup. |
| Q05 | REST and WS read the existing device snapshot. One lifespan task collects HTTP status. A complete batch replaces the snapshot only for matching endpoint identities. | No request-triggered probe, nonblocking read during resolution, complete publication, response close, replaced-profile race. |
| Q06 | Connection sends run independently with a two-second bound including lock wait. Existing per-connection ordering and state deduplication remain. | Slow state/error subscriber isolation, timeout cleanup, disconnect and publisher lifetime. |
| Q10 | Lifespan owns real startup and shutdown. Resolver retry uses the existing stop event and profile refresh implementation. Shutdown waits for in-flight work. | Import does not start processes/threads, deferred cancellation, single probe owner and in-flight shutdown wait. |
| Q14 | The adaptive-runtime CLI test writes JSON output under its `tmp_path`. | Real output initialization is retained and the temporary output file exists. |

Git rejection after a safe `.python` unlink leaves that link entry detached.
The shared target and the worktree's other data remain intact. No real worktree
cleanup command was used during validation.

The PulseAudio interface was checked against the upstream
[15.99.1 CLI command implementation](https://github.com/pulseaudio/pulseaudio/blob/v15.99.1/src/pulsecore/cli-command.c)
and [pacmd client](https://github.com/pulseaudio/pulseaudio/blob/v15.99.1/src/utils/pacmd.c).

## Validation environment

Windows validation uses the repository `.python\Scripts\python.exe`, with
`PYTHONDONTWRITEBYTECODE=1`. Interpreter identity and local package import checks
passed. Git Bash/junction checks require execution outside the restrictive
sandbox and use disposable test environments and substituted system commands.

| Executed check | Return code | Result |
| --- | --- | --- |
| Pre-change targeted baseline across agent, Bluetooth, CLI, Engine, Host, auth, WS, analysis and updater tests | 1 | 261 passed and 21 updater cases could not start Git Bash inside the sandbox, 56.39 s. |
| First-batch joint regression | 0 | 215 passed, 46.18 s. |
| State/WS/profile regression after removing the resolver-lock dependency from reads | 0 | 31 passed, 5.55 s. |
| Focused regression across all repaired boundaries | 0 | 75 passed, 12.19 s. |
| Fast suite | 0 | 388 passed, 8.10 s. |
| Initial full run with temporary output isolation | 1 | 1702 passed, 2 failed, 1 skipped, 595.78 s. |
| Recheck of Show/CLI/READY/Host health/lifecycle after the full-run fixes | 0 | 30 passed, 15.00 s. |
| Standard final full suite | 0 | 1704 passed, 1 skipped, 1 Starlette TestClient deprecation warning, 581.99 s. |
| `node --test kiosk/test/*.test.js` | 0 | 10 passed, 0.456 s. |

The two initial full-run failures were corrected by injecting adapter failure
at its new lifespan initialization boundary and retaining the CLI's distinction
between output initialization and rendering errors. Assertions were retained.
The final full run uses the standard pytest command without an output wrapper.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.python\Scripts\python.exe -B -m pytest -q --suite full --basetemp=tmp/pytest-quality-verified --inventory-json=tmp/quality-full-verified.json --durations=10 --tb=short
```

The inventory contains actual per-file setup/call/teardown measurements.
Earlier failing probes and fixture corrections are separate from final
acceptance evidence. `git diff --check` passes for the repair changes.

## Existing behavior and operational boundaries

The preserved `1108` implementations include Host mpv IPC, playback, pause,
resume, stop, seek, reset, audio setting, the natural-end watchdog and
`cmd_run_mpv`. Protected auth/video/IPC/Kiosk/updater files were also compared
against the backup branch. F01–F09 labels have no separate mapping file in the
repository, so preservation is tracked through the backup and behavior tests.

A readiness test before its isolation correction invoked the local resolver
and attempted to launch unavailable mpv. The ignored
`config/runtime/wled-ddp-mdns.yaml` was regenerated at 2026-11-08 13:55:44 local
time with all nine unresolved nodes disabled. Its pre-test bytes were outside
the Git backup and are unavailable for comparison. Corrected health tests inject
failure at the adapter constructor and bypass real resolution. Target Host
startup generates the runtime profile from its own mDNS environment.

An in-flight resolver can delay shutdown until its bounded subprocess finishes.
The command timeout is 30 seconds. Configuration/scene file reads during import
remain supported. Physical audio priority, WLED behavior and device lifecycle
acceptance remain **NOT HARDWARE VERIFIED**.
