# LIGHT-BELT Codex Instructions

This file defines stable repository-level constraints for future Codex
sessions. Keep it concise, executable, and aligned with the current approved
implementation plan.

## Documentation Authority

When documents or code disagree, use this order:

1. `CLAUDE.md`: permanent project facts and architecture constraints.
2. `docs/CLOSED_LOOP_SPEC.md`: closed-loop target behavior and protocol specs.
3. `docs/IMPLEMENTATION_PLAN.md`: the only authoritative implementation plan.
4. Current source code and tests: evidence of current behavior.

Do not copy the implementation plan into this file. Do not add line-number
references or details likely to drift.

For Show design, `assets/energy-wakeup/energy-wakeup.yaml` is the immutable
original source, while `config/shows/energy-wakeup.yaml` is the approved,
runnable copy and the only current Show compatibility baseline. Treat the
32 retired YAML files under categorized `config/shows/archive/` as legacy
replay/regression material, never as evidence for new visual or parameter
requirements. The `config/shows/` root contains only the approved current Show.

## Windows Python

On Windows, use only the bundled interpreter:

```powershell
.\.python\Scripts\python.exe
```

Never use bare `python`, `python3`, `py`, a Python executable from `C:`, or any
Python executable outside this repository.

Before the first Python command in each Codex session, verify the interpreter.
Codex on Windows may remap the repository into a sandbox path such as
`C:\Users\CodexSandboxOffline\.codex\.sandbox\cwd\<sandbox-id>`, so do not
require `sys.executable` to contain the original drive path or repository
directory name.

```powershell
.\.python\Scripts\python.exe -c "import sys, pathlib, light_engine; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe', cwd/'.python'/'python.exe']; existing=[c for c in candidates if c.exists()]; assert existing, 'No bundled Python found'; assert any(c.resolve()==exe for c in existing), 'Executable mismatch'; assert exe.name.lower()=='python.exe'; assert str(pkg).startswith(str(cwd)); print('executable=', exe); print('package=', pkg); print('PROJECT_PYTHON_OK')"
```

The command is valid when it was invoked as `.\.python\Scripts\python.exe`, the
current workspace contains `.python\Scripts\python.exe` (or the legacy
`.python\python.exe`), at least one of those candidate paths resolves to the
same file as `sys.executable` (tolerating Windows Junctions that share a venv
across worktrees), `light_engine` imports successfully, and the imported
package file is also under the current workspace mapping.

If the bundled interpreter is missing or fails, stop and report the error. Do
not fall back to another Python.

## Working Method

- Start by checking `git status`.
- Implement only the Phase explicitly approved by the user.
- Do not start, prepare, or partially implement later Phases without approval.
- Before spawning each new sub-agent, apply the complete tier-selection rules
  in the next section. Set both model family and reasoning effort explicitly;
  never inherit the primary agent's tier by default. Announce the selected tier
  and a brief reason in the commentary channel before spawning. Reusing an
  existing agent with a follow-up is not a new spawn and must be described as
  reuse rather than a new tier selection.
- Before modifying files, run the baseline tests with the bundled interpreter.
  Run this pre-change baseline at most once per Codex task/session: context
  compaction, task steering, follow-up prompts, and sub-agent work must reuse
  the recorded result instead of starting another baseline run. Relevant
  post-change tests and the final full-suite verification are not baseline runs
  and remain required:

  ```powershell
  .\.python\Scripts\python.exe -m pytest -q
  ```

- After each coherent change, run relevant tests and then the full test suite.
- Do not delete, skip, loosen, or weaken tests just to get a green result.
- Do not silently swallow errors or manufacture success.
- Do not silently fall back from production hardware transports to memory/fake
  transports.
- Keep changes Phase-scoped and avoid unrelated refactors.
- Do not run `git commit` unless the user explicitly asks for it.

## Sub-Agent Tier Selection

Choose the lowest model family and lowest reasoning tier that can reliably
finish the bounded subtask. Prefer Luna for explicit/mechanical work, Terra for
ordinary engineering, and Sol for ambiguity, cross-module reasoning, difficult
diagnosis, or high-risk judgment. Use Ultra or concurrent agents only when the
work contains genuinely independent parallel subtasks; otherwise raise the
reasoning tier of one agent. For every new agent, state the selected tier and a
short reason before spawning it.

Execution mapping: Light -> `low`, Medium -> `medium`, High -> `high`, Extra
High -> `xhigh`, and Max -> `max`. Ultra is a parallel-routing tier, not a
mandatory reasoning-effort literal: decompose it into independent agents and
give each agent the lowest supported effort required by its bounded subtask.
Model mapping: Luna -> `gpt-5.6-luna`, Terra -> `gpt-5.6-terra`, and Sol ->
`gpt-5.6-sol`. If the orchestration API cannot override a full-history fork,
use a bounded or no-history fork and include the required context explicitly;
do not fall back to inherited model or effort defaults.
In particular, Luna does not support an `ultra` reasoning-effort value, so a
Luna Ultra workload must use multiple Luna agents with supported per-agent
efforts; never pass an unsupported value. A provider's literal `ultra` effort,
when available, still requires the individual subtask itself to justify it.

- **Luna Light**：改名、改配置、格式化、机械替换、简单 grep 后修改。
- **Luna Medium**：明确需求的小功能、简单脚本、批量修改、补测试、普通报错修复。
- **Luna High**：边界清楚但涉及多个文件的实现、较复杂重构、需要一定自检的任务。
- **Luna Extra High**：明确但容易出错的复杂实现、较长依赖链排错、要求较强验证的机械型任务。
- **Luna Max**：任务逻辑明确但非常繁琐、需要长时间单线程推理和反复校验、不值得调用更贵模型时使用。
- **Luna Ultra**：大量彼此独立、明确、可并行的低难度子任务，如批量检查、测试、迁移、搜索和一致性修复。
- **Terra Light**：日常小功能、小 bug、常规配置和代码维护。
- **Terra Medium**：默认档，适合绝大多数功能开发、debug、多文件修改、API 接入和普通重构。
- **Terra High**：复杂 bug、跨模块功能、状态机、较大重构、需要理解项目结构后再修改。
- **Terra Extra High**：难定位问题、复杂依赖、并发/异步问题、需要多轮验证和较完整工程判断的任务。
- **Terra Max**：单个高难问题，需要深挖根因、设计方案、验证副作用并尽量一次做对。
- **Terra Ultra**：复杂项目任务可拆成多个相对独立方向时，并行做代码搜索、测试、架构分析、实现和审查。
- **Sol Light**：任务本身不难，但要求高质量判断、低返工或需要理解复杂上下文。
- **Sol Medium**：复杂代码开发、架构相关修改、模糊需求、重要功能和较难 bug 的高可靠默认档。
- **Sol High**：系统级问题、跨模块根因分析、大型重构、性能问题、复杂状态与边界条件。
- **Sol Extra High**：非常难的 bug、并发竞态、架构缺陷、跨软硬件/网络/系统层问题，需要深入推理和验证。
- **Sol Max**：单个极难且强耦合的问题，无法有效拆分，要求最大单 Agent 推理深度和最低返工率。
- **Sol Ultra**：大型开放任务，可拆成多个独立研究/实现方向，由多个 Agent 并行调查、编码、测试、审查，最后统一整合。

## Core Architecture

- Analog output is RGB+CCT five-channel control: `r`, `g`, `b`,
  `warm_white`, `cool_white`.
- Brightness is applied exactly once, in `OutputTransform`.
- Sequence numbers are assigned only by the Engine.
- One logical frame owns one shared sequence and media timestamp.
- RS-485 and UDP must use the same logical sequence for the same frame.
- Effects and analysis stay hardware-agnostic.
- `DigitalStrip` remains a pure logical model; it must not contain node IDs,
  hosts, ports, offsets, GPIO, or other physical topology.
- Physical details enter only `PhysicalFrame`, physical mapping, protocol, and
  transport layers.
- Protocol codecs must be pure and testable without hardware.
- Golden Vectors use JSON as the single source of truth for host and firmware.
- Production mode must fail explicitly; fake/memory transports require explicit
  config or dependency injection.
- Output queues keep only the latest complete logical frame.
- Do not interleave packets from different logical frames.
- A digital physical node receives one complete UDP frame and refreshes once.
- The default safe state is all black.
- Any behavior not verified on real hardware must be labeled
  `NOT HARDWARE VERIFIED`.

## Git Rules

- Check `git status` before work.
- Keep changes independently reviewable at Phase boundaries.
- Preserve user changes; never overwrite or revert work you did not make.
- Do not use destructive Git commands such as `git reset --hard` or
  `git checkout --` unless the user explicitly requests them.
- Do not stage, commit, push, or create PRs unless explicitly requested.

## Reporting

At the end of a task, report:

- Modified files.
- Actual commands run and their return codes.
- Test count and elapsed time for executed tests.
- Unresolved issues or limitations.
- `git diff --stat`.

If the final required benchmark or firmware build is in scope for the approved
Phase, also report its command, return code, and measured output. Never claim
hardware verification without real evidence.

