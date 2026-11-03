# 多智能体运行时 v1（M1）设计与实施记录

> 目标：把 KTP 现有的“同步单层委派”升级为可并发的子代理运行时——**子代理即任务、激活即返回、结算进收件箱、父代理只写自己的历史**。参考 DeepSeek Harness 的子代理语义，不引入其插件运行时。
>
> 状态：M1 已实现，默认关闭（`KTP_MULTI_AGENT_ASYNC=1` 打开）。日期 2026-11-03。

## 1. 现状（改动前）

| 能力 | 位置 | 问题 |
|---|---|---|
| 委派动作 | `v2/runtime/engine.py`（`action == "delegate"`） | 同步：`SubExecutor.execute()` 阻塞父代理主循环 |
| 子代理执行 | `v2/runtime/sub_executor.py` | 只返回结果，无独立句柄/生命周期 |
| 工具子集 | `v2/tools/registry.py::get_executor_subset` | 全局一套 `prosail./apsim./workspace.`，角色不可配 |
| 角色 | `v2/agents/registry.py` | 只有 name/role/description（planner_70b、executor_30b、reviewer），无提示词/工具/预算 |
| 结算 | 无 | 结果直接合进父 run 的 `tool_history`，没有“收件箱”概念 |

## 2. M1 实现

### 2.1 组件

| 文件 | 职责 |
|---|---|
| `v2/agents/registry.py` | 角色注册表：`system_prompt` / `tool_prefixes` / `max_steps` / `max_children`；内置 5 个角色（planner、executor_30b、remote_sensing_analyst、reporter、reviewer） |
| `v2/agents/inbox.py` | `AgentSettlement` + `AgentInbox`（线程安全的按父 run 队列，`push/drain/pending/wait`） |
| `v2/agents/runtime.py` | `SubAgentRuntime.spawn(...) -> AgentHandle`：子代理在独立线程跑 `SubExecutor`，完成时投递 settlement；并发上限、深度上限、取消桥接 |
| `v2/tools/registry.py` | `subset_by_prefixes(prefixes)`：按角色裁剪工具；空列表 = 无工具（reviewer） |
| `v2/runtime/engine.py` | 委派分支：有 runtime 时只 spawn + 继续规划；每步开始 drain 收件箱；有未结算子代理时禁止结束回复；`_finalize_run` 取消子代理 |
| `ktp_backend/runtime_host.py` | 按 `KTP_MULTI_AGENT_ASYNC` 构造并注入 `SubAgentRuntime` |

### 2.2 语义（与 harness 对齐）

1. **激活即返回**：`delegate` 不再阻塞；父代理立刻拿到 `[已委派 role] ...（等待结算）` 并继续规划。
2. **结算消息**：子代理完成 → `AgentSettlement` 进父收件箱 → 父代理下一步开始时 drain，作为 tool 消息注入。
3. **父代理不得带未结算子任务结束**：planner 若在 pending>0 时回 `reply`，引擎等待结算后再继续规划。
4. **角色隔离**：每个子代理有自己的 `ChatFirstPlanner`（角色提示词 + 步数上限）与裁剪后的工具注册表。
5. **失败不炸父代理**：子代理异常转为 error settlement（`success=False`），父代理可继续或重派。
6. **取消级联**：每个子代理有独立取消事件，并由父 run 的取消事件桥接；`_finalize_run` 统一 cancel。

### 2.3 限制（M1 明确不做）

- 子代理不能再委派（深度上限 1）。
- 子代理运行记录不独立持久化（以父 run 的 trace/tool_history 为准）。
- 无跨进程/跨租户调度；同一父 run 最多 3 个并发子代理。
- 新增 SSE 事件类型未加（复用 `run.progress`），前端卡片在 M3。

## 3. 验收

| 检查 | 结果 |
|---|---|
| 新增测试 `v2/tests/test_multi_agent_runtime.py` | 7 项：角色/工具子集、收件箱语义、spawn→settle、planner 不可作目标、并发上限、取消桥接 |
| `backend/v2/tests` | 96 → **103 passed** |
| `backend/tests` | **358 passed / 3 skipped**（行为不变，flag 默认关闭） |
| 线上行为 | 默认关闭 = 原同步委派路径；打开后走异步路径 |

## 4. 后续阶段

| 阶段 | 内容 | 验收 |
|---|---|---|
| M2 | 角色提示词调优 + planner 可见 agents 与委派策略（何时拆/何时自己做）+ settlement 注入会话（父 run 结束后子结果仍可唤醒下一轮） | 真实会话里一次 3 角色协作，SSE 可见 spawn/settle |
| M3 | 子代理独立 run 记录与事件（`agent.spawned/agent.settled` + `parent_run_id`）、前端子代理卡片、嵌套委派与预算 | 前端可展开子代理轨迹；深度 2 可用 |
| M4 | 与专业链打通：协调者按 crop/LAI/报告工具拆活，验证“工具注册表 + 多代理”协同 | 一个专业任务由 ≥2 个子代理完成且产物可追溯 |

## 5. 风险与回滚

- 打开开关才生效；关闭即回退到原同步路径（`agent_runtime=None`）。
- 子代理线程为 daemon，父 run 结束会 cancel；异常均转 settlement，不会被静默吞掉。
- 已知风险：planner 可能在结算前反复 delegate，导致子代理数量增长——并发上限 3 + 步数上限 10 兜底；M2 加预算与“委派前确认”策略。
