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
- Before spawning each new sub-agent, apply the `Subagent Strategy` below.
  Set both model family and reasoning effort explicitly; never inherit the
  primary agent's model or reasoning effort by default. Announce the selected
  model and reasoning effort and a brief reason in the commentary channel
  before spawning. Reusing an existing agent with a follow-up is not a new
  spawn and must be described as reuse rather than a new model selection.
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

## Subagent Strategy

在满足正确性、项目约束和验收要求的前提下，优化完成任务的总成本与耗时。
总成本包含模型调用、上下文传递、等待、重复调查、返工和回归修复。
不以最低单次调用价格、最高推理强度或最多代理数量作为目标。

### 1. 先决定是否委派

- 简单读取、搜索、执行命令、运行已知检查，优先直接使用工具。
- 主代理已掌握必要上下文，且剩余工作较小时，直接完成。
- 仅当子任务边界明确、产出可验收，且预期收益超过启动、交接和整合成本时委派。
- 优先将委派与主代理可继续推进的有效工作并行；即使主代理需要等待，当专业化模型、独立复核、长耗时验证或上下文隔离具有明确收益时，也允许委派。
- 不为一个简单命令创建代理，不为满足分工形式拆开小修复与其测试。
- 本节明确授权在满足上述条件时使用子代理，无须逐次向用户确认；
  仍须遵守当前 Phase、工具限制和既有权限边界。

### 2. 模型选择

以下是初始路由偏好，不是必须逐级经过的能力阶梯：

| 模型 | 优先适用场景 | 常用 effort |
| --- | --- | --- |
| Luna | 足够成批、目标确定的机械工作；按已知契约修改或验证 | low / medium |
| Terra | 常规实现、局部调试、行为边界明确的多文件变更 | medium |
| Sol | 多状态或跨模块推理、复杂实现、需要架构判断的审查 | medium / high |
| Astra | 问题边界不清或高度耦合的诊断/实现、跨层根因分析、困难架构裁决、重要约束冲突，或既有推理已显不足 | medium / high |

- 根据当前证据、问题难度、错误代价和交接成本选择模型。
- 根因未知、文件多、任务长、需要全套测试，不单独构成升级理由。
- 已知高难任务可以直接使用 Astra，无须先尝试较弱模型。
- 不限制 Astra 只能分析，也不强制它完成分析后交接实现。
- 主代理的模型不决定子代理的模型；每项委派独立选型。

### 3. 推理强度

- low：机械、确定、验证路径明确。
- medium：常规工程判断，默认选择。
- high：多个状态、约束或假设需要综合判断。
- xhigh / max：任务本身或已有调查证据表明存在异常复杂的推理需求；
  说明具体难点，无须为了取得失败记录而先使用低档。
- 仅使用当前工具支持的参数；不假定不同模型的 effort 存在固定等价关系。
- 并行数量独立决定，不使用“某模型 Ultra”表示并行策略。

### 4. 并行与所有权

- 从最少必要代理开始，只有出现新的独立工作流才增加。
- 并行工作必须具有不同问题或产出，并能实际缩短完成时间或降低重要风险。
- 考虑共享文件、CPU、硬件、端口和测试环境的竞争。
- 每个写入范围只有一个负责人；需要修改重叠范围时先协调。
- 强耦合问题由一个负责人维护事实、假设和最终结论；
  该负责人通常可以是主代理。
- 其他代理只调查明确的证据缺口，不重复重建整个问题。
- 对关键结论的独立复核允许有目的的重复，但必须说明复核价值。
- 子任务失去价值或已被其他结果覆盖时，及时停止或重新限定范围。

### 5. 委派与交接

每次委派用简短任务说明提供：

- 目标、范围以及允许修改的文件；
- 已知事实、必要约束和证据位置；
- 交付物与验收条件。

升级或移交时追加已尝试方案、排除依据、当前改动和未解决问题。
优先提供必要摘要和可定位证据，避免复制全部历史或要求重读整个仓库。
区分观察事实与推测；验证完成不等于根因已经证明。

每次新建代理显式指定模型和 effort，并用一句话说明选择理由。
复用代理时说明复用，不宣称已切换模型或 effort；
只有工具实际支持并确认的变化才可报告为已生效。

### 6. 重新评估与升级

- 假设被证据排除属于正常进展，不自动升级。
- 两次有实质区别的尝试仍未缩小问题范围，或任务明显超出原定边界时，
  重新评估证据、拆分、模型和 effort。
- 缺少日志、复现、设备观测或外部条件时，先获取必要证据；
  更强模型不能替代缺失的事实。
- 推理能力不足时提高 effort 或切换模型；问题过度耦合时减少并行；
  任务范围不清时先重新限定问题。
- 升级必须改变可说明的条件，不重复无新证据的失败尝试。
- 诊断完成后，仅当剩余工作足以抵消交接成本时再交给其他模型。

### 7. 验证与审查

- 实现负责人通常同时负责相关回归测试。
- 只有验证工作足够独立且值得并行时，另行委派。
- 测试依据规范、契约或独立预期，不仅复述实现。
- 实质改变协议、并发顺序、时序、安全状态或兼容性保证时，
  安排有明确问题的独立审查；文字或机械变化不因文件名触发审查。
- 审查者自行核对规范与差异，区分诊断假设与事实，不只认可作者结论。
- 独立审查的目标是寻找反例、遗漏和不成立的假设，不自动取得根因所有权。除非审查者提供足以推翻当前结论的新证据，否则由原负责人继续维护统一事实模型。
- 主代理负责整合和最终验收，不将子代理声称成功直接当作验证证据。
- 复用本任务已经完成的基线结果；全套测试由主代理统一协调，
  遵守 Working Method，避免各代理重复运行同一套基线或全量检查。
- 无真实硬件证据时，保持 NOT HARDWARE VERIFIED 标记。

### 8. 模型与工具兼容

```text
Luna  -> gpt-5.6-luna
Terra -> gpt-5.6-terra
Sol   -> gpt-5.6-sol
Astra -> gpt-6-astra
```

以当前编排工具实际支持的模型和 effort 为准。
若全历史 fork 不允许覆盖模型或 effort，使用有界或无历史 fork，
并提供必要上下文，不静默退回主代理默认配置。

### 9. 依据结果调整

对具有代表性的实际委派，简要记录：
任务类型、模型与 effort、耗时、验收结果、返工和可获得的用量。

按同类任务的总体表现调整路由，不根据一次成功或失败制定固定结论。
日常任务不默认进行多模型重复竞赛。

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

