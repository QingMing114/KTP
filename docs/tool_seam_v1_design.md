# 工具接入 Seam v1 设计（S1：收口 + 呈现/装配声明）

> 日期：2026-10-26。状态：实施中（S1）。
> 背景：契约 `algorithm-tool/v1`（[algorithm_tool_contract_v1.md](algorithm_tool_contract_v1.md)）解决了“算法数据怎么安全流动”，但没有解决三件事：能力边界（谁能替换谁）、装配清单（当前到底装了哪些能力）、呈现声明（工具该怎么显示）。本设计借用 DeepSeek Harness 的 seam/注册/呈现思想，**不引入 Cordis 运行时、profile 层叠或客户端 slot**。

## 1. 目标与非目标

**目标（S1，行为不变）**
1. 为 5 个“外部会变”的能力定义 seam（Service Definition）：LLM、Dataset、Artifact、Memory、Tool。
2. 提供 seam 注册表 + 装配清单（composition），启动时校验、失败即报错。
3. 给 `ToolSpecV2` 增加可选的呈现声明（presentation），让前端可以按声明渲染而不是按工具名硬编码。
4. 全部改动可增量回退：不改变现有执行路径、不改变任何工具行为。

**非目标（后续切片）**
- S2：工具管线中间件（pre/execute/post/error 有序链）接线到 `ToolExecutor`。
- S3：统一步骤事件（`step.queued/progress/awaiting_confirmation/completed/failed` + `seq` + SSE）。
- 不做插件树、不做 HMR、不做 profile/bundle/patch 层叠、不做客户端 slot。

## 2. 现状问题（代码证据）

1. **能力没有边界**：`engine.py` 直接持有 `AgentLLMProvider`、`AlgorithmDatasetResolver`、`ArtifactStore`、`MemoryManager` 的具体类型；换实现要改引擎（`v2/runtime/engine.py:97`、`:770-782`、`:462-479`）。唯一已是 Protocol 的是 `AgentLLMProvider`（`infra/llm/provider.py:76-96`）。
2. **没有装配清单**：当前装了哪些能力、哪些工具对谁可见，只能读 `build_default_tool_registry()` 的字面量（`v2/tools/registry.py:215-779`）和 `_resolve_visible_tools()` 的硬编码白名单（`engine.py:1271-1285`）。新增/停用一个能力没有单一入口，也无法在启动时校验。
3. **工具没有呈现声明**：`ToolSpecV2` 有 `display_name/usage_hint/safety_level/produces_artifacts`（`schemas/runtime.py:217-240`），但没有“卡片类型、摘要字段、进度阶段”，导致前端按 `step_id`/工具名硬编码（见 `_dsh_review/ktp-tools-frontend.md`）。

## 3. 借什么、不借什么

| DSH 机制 | 本设计采纳 | 落点 |
|---|---|---|
| capability seam 三角（Definition/Provider/Consumer） | ✅ 只借“定义与实现的分离” | `v2/seams/protocols.py` |
| 注册即副作用、可撤销 | ✅ 借“可撤销”语义（`unregister()` 已有），不做 effect 树 | `SeamRegistry` |
| profile/bundle 装配 | ✅ 降级为**一份显式清单**，不做 YAML 层叠 | `v2/composition.py` |
| 有序 waterfall 扩展点 | ⏳ S2，用显式 middleware 链 | `v2/middleware/`（S2） |
| presentation 声明 + 通用卡回退 | ✅ 借声明，前端做注册表 + 回退 | `ToolPresentation` + 前端（S1 只落 schema） |
| Cordis 运行时 / 插件树 / HMR | ❌ 不借 | — |
| 客户端 slot 系统 | ❌ 不借（Vite 单应用） | — |

## 4. 第一层：5 个 seam

定义在 `backend/v2/seams/protocols.py`，全部为 `typing.Protocol` + `@runtime_checkable`：

| seam | 方法（Definition） | 现有 Provider | 消费者 |
|---|---|---|---|
| `LLMSeam` | `generate_text`, `generate_structured` | `SubprocessQwenVLProvider` 等 | `planner`、`sub_executor`、`crop_decision` |
| `DatasetSeam` | `resolve(tool_input, execution_context, **bounds)` | `AlgorithmDatasetResolver` | `invoke_algorithm` 路径 |
| `ArtifactSeam` | `register`, `get`, `list_by_run`, `list_all` | `ArtifactStore` | `ToolExecutor`、canonical 路由 |
| `MemorySeam` | `reload`, `entries`, `is_loaded`, `get`, `find_relevant`, `build_context_injection` | `MemoryManager` | `engine` 的 Memory 注入 |
| `ToolSeam` | `list_tools`, `get_definition`, `has_tool`, `register`, `unregister`, `invoke`, `invoke_algorithm` | `ToolRegistryV2` | `engine`、`ToolExecutor`、`PolicyGuard` |

约定：

- Protocol 只做**结构校验**（`isinstance` 检查方法存在），不改变运行时类型；实现仍是现有类。
- 新增能力必须先加 Definition，再加 Provider，再改 Consumer —— 一次改齐，否则不算 seam（DSH 的教训）。
- 不把工具本身做成插件：工具继续走注册表 + 契约；seam 只覆盖“外部会变”的能力。

## 5. 第二层：装配清单（composition）

`backend/v2/composition.py`：

```python
class ToolExposure(BaseModel):
    default: Literal["model", "workflow", "endpoint"] = "model"
    disabled: list[str] = []        # 显式停用（拼错即报错）
    endpoint_only: list[str] = []   # 只给端点/工作流用，不给模型

class CompositionSpec(BaseModel):
    name: str = "ktp-default"
    required_capabilities: list[str] = ["tools"]
    optional_capabilities: list[str] = ["llm", "datasets", "artifacts", "memory"]
    tools: ToolExposure = ToolExposure()
```

校验规则（启动时执行，失败 loud）：

- `required_capabilities` 必须全部在 `SeamRegistry` 中且有实现；
- `disabled` / `endpoint_only` 里的名字必须存在于工具注册表（拼错 = 配置错误，不静默忽略）；
- 同一工具不能同时出现在 `disabled` 与 `endpoint_only`；
- 注册表中存在但清单未提及的工具 → 返回 warning（不阻塞），用于发现“漏登记”。

与 DSH profile 的差异：**只有一层**、无 patch 合并、无运行时重载；改动需要重启并走验收。

## 6. 第三层：呈现声明

`schemas/runtime.py` 新增：

```python
class ToolPresentation(BaseModel):
    card_kind: str = "generic"          # generic/analysis/report/geo/table/...
    summary_fields: list[str] = []      # 折叠行摘要取哪些结果字段
    progress_phases: list[str] = []     # 阶段名，用于进度展示
    result_renderer: str | None = None  # 前端 renderer 注册键，缺省 = card_kind
    expandable: bool = True             # 是否有详情视图
```

`ToolSpecV2.presentation: ToolPresentation | None = None`（默认 None，老工具行为不变）。

前端消费方式（S1 只落约定，S2/S3 接线）：`renderer = registry[spec.presentation?.result_renderer ?? spec.name] ?? GenericStepCard`；未知工具回退通用卡，不允许抛错。

## 7. 改动清单（S1）

| 文件 | 改动 | 风险 |
|---|---|---|
| `backend/v2/seams/protocols.py`（新） | 5 个 Protocol + 说明 | 无（新增） |
| `backend/v2/seams/registry.py`（新） | `SeamProvider`、`SeamRegistry`、`build_default_seams` | 无（新增） |
| `backend/v2/seams/__init__.py`（新） | 导出 | 无 |
| `backend/v2/composition.py`（新） | `CompositionSpec`、`ToolExposure`、`validate_composition` | 无（新增，暂不接入启动路径） |
| `backend/schemas/runtime.py` | 新增 `ToolPresentation`；`ToolSpecV2.presentation` | 低（可选字段） |
| `backend/v2/tools/registry.py` | 给 2 个代表工具补 `presentation` | 低（字面量新增参数） |
| `backend/v2/tests/test_seam_protocols.py`（新） | 现有实现满足 Protocol | 无 |
| `backend/v2/tests/test_composition_manifest.py`（新） | 装配校验（缺能力/拼错/冲突/警告） | 无 |

**不在 S1 接线**：`engine` 仍直接用具体类型；`composition` 仍不参与启动。这样任何一步都可单独回退，且不改变任何现有测试的期望。

## 8. 验收

1. `pytest backend/v2/tests/test_seam_protocols.py backend/v2/tests/test_composition_manifest.py -q` 全绿；
2. 既有基线不回退（至少运行 `backend/v2/tests` 与 `backend/tests/test_professional_reviews.py`）；
3. `ToolSpecV2` 序列化向后兼容：不带 `presentation` 的旧工具 `model_dump()` 不新增非空字段歧义（新增字段为 `None`）；
4. 反向用例：缺 capability、拼错工具名、`disabled`/`endpoint_only` 冲突均报可读错误。

## 9. 回滚

- 代码回滚点：提交 `7712584`（备份分支 `backup/2026-10-26-pre-tool-seam`）；
- S1 全部为新增文件 + 可选字段，`git revert` 单提交即可回退，无数据迁移。

## 10. 风险与后续

- **风险 1：Protocol 只做结构校验**，签名不匹配要等到运行时才炸 → 用测试覆盖每个 Provider 的关键方法可调用性（构造 + 调用一次）。
- **风险 2：装配清单与真实注册表漂移** → 用测试锁定“清单里每个名字都存在”，并要求新增工具时同步登记。
- **后续 S2**：把 `ToolExecutor` 改造成 `pre → guard → execute → post → result` 链，中间件注册进 composition。
- **后续 S3**：统一步骤事件（带 `seq` 与 SSE），替换 `created/step_updated/status_updated`。

## 11. S2 实施记录（2026-10-26）

- `ToolExecutor.execute_tool_call` 拆为 `_build_state → pipeline.run → _result_payload`；`_dispatch_tool_call` / `_finalize_tool_call` 承接原有分发与收尾逻辑，逐段迁移、行为不变。
- 新增 `v2/middleware/tool_pipeline.py`（`ToolCallState` / `ToolMiddleware` / `ToolPipeline`）与 `builtin.py`（`PermissionMiddleware`、`PolicyGuardMiddleware`、`build_default_tool_pipeline`）。
- 权限与策略校验从 executor 搬到中间件；`PolicyGuardError` 拒绝改为 `skip_dispatch + error observation`，与原先内联 try 的语义一致。
- `append_assistant_part` 移到 `v2/runtime/run_parts.py`，executor 保留模块级导入作为再导出，避免中间件与 executor 循环导入。
- 装配清单新增 `middlewares` 字段，校验未知名称与重复名称。
- 验证：`backend/tests` 306 passed / 3 skipped；`backend/v2/tests` 96 passed（新增 10 项管线测试）。

## 12. A 阶段实施记录：作物识别接入（2026-10-26）

| 步骤 | 内容 | 提交 |
|---|---|---|
| A1 | 抽出单一实现 `runtime/crop_classification.py`：空间推理 → 判定 → provenance → 报告登记；支持 STAC item 与已准备 reflectance 两种输入；端点与工作流都改调它 | `e574615` |
| A2 | 新增 `v2/tools/crop_tool.py`：`CropToolInput`（`additionalProperties: false`）、`ToolSpecV2`（`category=remote_sensing`、`permissions=[dataset:read, artifact:write]`、`presentation`）、handler 委托 `classify_crop` | 本次 |
| A3 | 在 `install_canonical_product_api` 中装配：复用 host 的 `tool_registry`（裸应用则建一个 canonical registry），注册时绑定 `ArtifactStore`、产物根目录与**惰性** LLM provider 解析器；未配置时注册 `unavailable` 版本 | 本次 |
| A4 | `POST /crop-analyses` 改为 `registry.invoke(CROP_TOOL_NAME, ..., progress_callback=...)`；工作流仍调用 `classify_crop(reflectance_path=...)`，因为共享影像已准备好，强行走工具会退化为重新下载 | 本次 |
| A5 | 模型可见性是显式开关：默认 `surface_visibility="debug"`（planner 不可见）；设置 `KTP_CROP_TOOL_MODEL_VISIBLE=true` 切到 `all`。打开前需先解决"模型无法提供 host-resolved item"与确认语义 | 本次 |

已知边界（后续处理）：工具 handler 目前返回空 artifacts 列表，报告引用在 observation payload 里；若希望 `artifact.available` 事件与 run.artifacts 也覆盖报告，需要在 handler 里把报告引用转换成 `PackArtifactView`。

流程沉淀：把 S1/S2 与 A 阶段的作业顺序整理成了 [工具接入手册.md](工具接入手册.md)（三种工具形态、五阶段交付、spec 清单、装配与打桩规则、检查清单）。
