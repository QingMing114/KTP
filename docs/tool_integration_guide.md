# 工具接入手册 v1（2026-10-27）

> **定位**：把「一个新能力怎么变成系统里可发现、可调度、可观测、可回退的工具」写成固定流程。本手册是流程层；字段级契约见 [algorithm_tool_contract_v1.md](algorithm_tool_contract_v1.md)，架构决策见 [tool_seam_v1_design.md](tool_seam_v1_design.md)，具体算法的准入材料见 [integration/](integration/) 下的 `ALG-2xx` 手册。
>
> **依据**：2026-10-26 的 S1（seam + 装配清单 + 呈现声明）、S2（工具管线中间件）、A1–A5（作物识别接入）实施经验。参考实现与提交见附录 A。
>
> **一句话**：先抽单一实现，再声明契约，再装配注册，再把入口改薄，最后才决定模型能不能看见。

---

## 1. 先选形态，再写代码

| 形态 | 适用 | 输入 | 执行路径 | 权限/审批 | 例子 |
|---|---|---|---|---|---|
| **A. `algorithm-tool/v1`** | 纯计算：输入是受控数据引用，输出是算法结果 | `dataset_refs + parameters + output_options` | `registry.invoke_algorithm(...)`（Runtime 注入 `ToolExecutionContext` 与取消/进度控制） | required/granted 差集在 Runtime 边界强制 | `prosail.*`、`apsim.*`、未来 `ALG-211/212/213` |
| **B. host-invoked product tool** | 需要宿主对象或已校验上下文（影像快照、产物存储、租户）,或串联了多个步骤（推理+判定+报告） | 宿主构造的 JSON 输入 + 宿主私有参数 | `registry.invoke(...)`（可选 `progress_callback`） | `spec.permissions` 声明；当前 `invoke` 不做差集，靠中间件/形态 A 补 | `remote_sensing.crop_classification` |
| **C. `legacy`** | 存量工具，不强制迁移 | 各自形状 | 原有路径 | 原样 | `ktp.*`、`workspace.*` |

**判据**（任一为「是」→ 选 B）：
1. 模型**无法独立构造**输入（例如需要服务端签发的 `imagery_snapshot`）；
2. 需要**宿主依赖**（`ArtifactStore`、`RequestContextV2` 里的私有对象）；
3. 工具内部有**多段编排**（推理 → 大模型判定 → 报告），不属于单一算法。

选错形态的代价：B 硬套 A，就要伪造 `dataset_refs`；A 硬套 B，就丢掉 required/granted 权限差集。

---

## 2. 五阶段交付（每阶段独立可回退）

| 阶段 | 目标 | 主要产物 | 验收 | 线上行为 |
|---|---|---|---|---|
| **P1 单一实现** | 把能力从各处调用点抽成一个服务函数 | `backend/runtime/<capability>.py` | 全仓只剩一个实现调用点；端点/工作流/工具都能调它 | 不变 |
| **P2 契约与 handler** | 声明 spec、输入/输出模型、handler、呈现 | `backend/v2/tools/<tool>.py` | spec 校验通过；handler 单测（委托、缺参、进度） | 不变（尚未接线） |
| **P3 注册与装配** | 把工具装进注册表，依赖注入，未配置时降级 | 装配点一处（见 §3） | 注册后 `registry.has_tool`；`unavailable` 时原因可读 | 不变（可见性 `debug`） |
| **P4 入口薄壳** | HTTP/工作流改为经注册表调用 | 端点/runner 各一处 | 响应字段、进度序列、错误分类与改造前一致；全量回归绿 | 不变（路径变了，语义一致） |
| **P5 可见性开关** | 决定模型/工作流/端点谁能用 | 配置或环境变量 + 测试 | 两种可见性都有断言 | **会变**：打开即行为变更 |

铁律：**P1 不做完不开 P2**。否则注册表里会出现第三份实现，所有后续验收都失去意义。

---

## 3. 代码落点与所有权

| 落点 | 放什么 | 是否热点（串行） |
|---|---|---|
| `backend/runtime/<capability>.py`（新） | 单一实现；不依赖 registry，只接收显式参数 | 否，可并行 |
| `backend/v2/tools/<tool>.py`（新） | `ToolSpecV2`、输入模型、handler、`configure_*` / `register_unavailable_*` | 否 |
| `backend/v2/tools/registry.py` | 注册入口（集中装配） | **是** |
| `backend/api/canonical/router.py` | 装配调用 + 端点薄壳 | **是** |
| `backend/v2/runtime/executor.py` | 只放管线；**新工具不要改它** | **是** |
| `backend/v2/middleware/` | 横切能力（权限、策略、未来的脱敏/审计） | 否 |
| `backend/tests/` | 服务、端点、工具注册/装配测试 | 否 |
| `backend/v2/tests/` | 管线、seam、装配清单测试 | 否 |

规则：**一个工具一个 handler**；端点与工作流都只调注册表或该实现，不再各自复制序列。

---

## 4. spec 清单（逐字段）

```python
ToolSpecV2(
    name="remote_sensing.crop_classification",   # 稳定能力名：<domain>.<capability>
    display_name="作物识别",
    description="做什么（给模型）",
    usage_hint="何时用 / 何时别用 / 边界（给模型）",
    visibility="bounded",              # public | bounded | internal
    category="remote_sensing",         # engine 的 category 白名单依据
    surface_visibility="debug",        # all | web | api | debug | internal
    enabled_by_default=True,
    contract_version="legacy",         # 形态 A 用 "algorithm-tool/v1"
    input_schema=CropToolInput.model_json_schema(),   # additionalProperties: false
    output_schema={...},
    safety_level="caution",            # safe | caution | dangerous（危险工具会被阻断）
    user_confirmation_required=False,
    permissions=["dataset:read", "artifact:write"],   # 只写 required
    availability="available",          # available | unavailable | disabled
    unavailable_reason=None,           # unavailable 必填原因
    produces_artifacts=["crop_classification_report"],
    presentation=ToolPresentation(     # 前端按声明渲染，而不是按名字硬编码
        card_kind="analysis",
        summary_fields=["crop_decision.final_name_zh"],
        progress_phases=["准备影像", "模型推理", "生成判定", "写报告"],
        result_renderer="crop_decision",
        expandable=True,
    ),
)
```

**禁止**：把宿主路径、凭据、内部地址写进 schema；把 UI 文案写进 `description`（模型可见内容与 UI 文案分开）；用 `display_name` 当唯一标识（一切按 `name`）。

---

## 5. 装配与依赖注入（本次踩坑最多的一节）

**装配点只能有一个**：本项目的工具在 `install_canonical_product_api()` 里、产物存储创建之后装配。

```python
def _ensure_tool_registry_with_crop_tool(app: FastAPI) -> None:
    registry = getattr(app.state, "tool_registry", None)
    if registry is None:                      # 裸应用（测试/嵌入式）也保证单一执行链
        registry = build_default_tool_registry()
        app.state.tool_registry = registry
    configure_crop_tool(
        registry,
        artifact_store=app.state.product_artifact_store,
        artifact_root=artifact_root,
        llm_provider_resolver=lambda: getattr(      # 惰性：引擎可能在安装后才挂
            getattr(app.state, "runtime_engine", None), "llm_provider", None
        ),
        model_visible=os.getenv("KTP_CROP_TOOL_MODEL_VISIBLE", "false") == "true",
    )
```

四条规则：

1. **复用 host 的 registry**；没有 host 时才建 canonical registry。不要出现第二个注册表。
2. **依赖用惰性解析**：安装顺序导致的 `None` 是最隐蔽的 bug（本次 `llm_provider` 就是后挂的）。
3. **未配置时注册 `unavailable`**，写清原因；不要静默缺失——缺失会让"模型看不见"和"配置错了"无法区分。
4. **不要在 `build_default_tool_registry()` 里捕获会变化的依赖**；那里只放静态能力。

---

## 6. 执行管线（S2 之后）

```
registry.invoke / invoke_algorithm
        │
        ├─ before: permission → policy-guard        ← 中间件负责，工具不写
        ├─ dispatch: handler(**tool_input)          ← 工具只做业务
        ├─ finalize: invocation / trace / tool.completed / artifacts
        └─ after: （预留：脱敏、审计、成本统计）
```

- **进度**：`registry.invoke(..., progress_callback=...)`；handler 接收 `*, item=None, progress_callback=None, **tool_input`。
- **错误**：工具内异常由 dispatch 收敛为 `error` observation（**不终止整个 run**）；取消抛 `RuntimeCancellationError` 透传，不要吞掉。
- **不要绕过注册表直接调实现**。唯一允许的例外是"输入形态确实不同"的适配器（本次：工作流已准备好 `reflectance.tif`，强行走工具会退化为重新下载），且必须在文档里写明理由。

---

## 7. 事件、错误码、产物

| 项 | 要求 |
|---|---|
| 事件 | 工具经 executor 调用时自动产生 `tool.started` / `tool.progress` / `tool.completed` / `artifact.available`；端点直调时至少保证进度回调与终态记录 |
| 错误码 | 形态 A 用 12 个冻结码（`INVALID_INPUT`…`CONTRACT_VERSION_MISMATCH`）；形态 B 用稳定 `code + 可操作文案`（说清下一步，不只报现象） |
| 产物 | 报告/栅格必须经 `ArtifactStore` 登记（含 SHA-256、媒体类型、空间元数据）；provenance 至少覆盖工具、算法、模型、数据、参数版本 |
| 已知边界 | 若 handler 返回空 `artifacts`（如作物识别当前实现），报告引用只在 observation payload 里，不会触发 `artifact.available`；需要时把引用转成 `PackArtifactView` |

---

## 8. 测试矩阵

| 层级 | 必测 | 命令（工作目录 `ktp/backend`） |
|---|---|---|
| 服务实现 | 两种输入形态、判定/provenance/报告组合、进度顺序 | `python -m pytest tests/test_<capability>_service.py -q` |
| 工具契约 | spec 字段、权限、可见性开关、presentation、缺参失败、unavailable 拒绝、装配接线 | `python -m pytest tests/test_<tool>.py -q` |
| 行为等价 | 端点/工作流/报告全部原有用例不回退 | `python -m pytest tests -q` |
| 管线/装配 | 中间件顺序、短路、skip、seam 一致性、装配校验 | 在仓库根：`python -m pytest backend/v2/tests -q` |

**打桩规则（本次最贵的教训）**：
- 只 patch **拥有这次调用** 的模块。实现从 `runner` 移到 `crop_classification` 后，6 处旧打桩点全部改到新模块；
- **禁止加 re-export 兼容层**让旧打桩点继续"通过"——那会变成假绿，测试什么都没测到；
- 改动后先看失败原因再改测试，不要先改断言。

---

## 9. 验收与证据

当前受控基线（2026-10-26，提交 `1e97b04`）：

- `backend/tests`：**322 passed / 3 skipped**
- `backend/v2/tests`：**96 passed**

单个工具接入的完成定义：

- [ ] 全仓只剩一个实现调用点（`grep` 可证）
- [ ] spec 出现在 `/v2/tools` 与 manifest，带 presentation
- [ ] 端点/工作流响应字段与改造前一致（原有测试全绿）
- [ ] 一个真实工作流跑通（记录 workflow ID、trace、报告 URL）
- [ ] 反向用例：`unavailable` 原因、缺参、权限拒绝
- [ ] 前端刷新/断线后状态与改造前一致

---

## 10. 交付、回滚与部署

- **提交粒度**：一个阶段一个提交（P1/P2/P3/P4/P5 可分别 `revert`）；提交信息带阶段编号与工具名。
- **回滚**：功能开关（可见性）+ 单提交 revert 双保险；接入前打备份分支（如 `backup/<date>-pre-<tool>`）。
- **gpu208 同步**：只有**影响运行行为**的变更才必须同步；P1–P4 是行为等价重构，可与下一次真实接口变更一起部署，减少重启次数。P5 打开可见性属于行为变更，必须单独验收后再同步。

---

## 11. 常见坑（本次实测）

1. **打桩点错位 → 假绿**：实现搬家后旧 patch 目标不存在，测试报 `AttributeError`；改测试前先确认"谁拥有这次调用"。
2. **re-export 兼容层**：让旧打桩点继续生效，等于测试一个已不存在的调用。
3. **安装顺序**：装配时拿到的 `llm_provider` 是 `None` → 必须惰性解析。
4. **双入口重复下载**：工作流已有共享影像，硬走工具接口会重复下载；保留 prepared-raster 适配器并写明理由。
5. **artifacts 为空**：报告引用只在 payload，`artifact.available` 不触发；需要时补 `PackArtifactView`。
6. **热点冲突**：`registry.py`、`router.py`、`executor.py` 串行改，不能与其他工作包并行。
7. **权限只声明不强制**：形态 B 的 `invoke` 目前不做 required/granted 差集；敏感工具应走形态 A，或在中间件补校验。
8. **过早打开可见性**：模型会调用一个必然失败的工具（缺 host 输入），表现为"模型乱试"。

---

## 12. 检查清单（复制即用）

**P1 单一实现**
- [ ] 新服务函数签名只接收显式参数（不 import registry）
- [ ] 两个以上入口改为调用它
- [ ] `grep` 确认底层函数只剩一个调用点
- [ ] 行为等价回归绿

**P2 契约与 handler**
- [ ] `name/description/usage_hint` 写清"何时用/何时别用"
- [ ] 输入模型 `additionalProperties: false`
- [ ] 输出结构可被前端与报告消费（字段名与现有响应一致）
- [ ] `permissions` 只写 required；`availability` 三态明确
- [ ] `presentation` 声明 card_kind/summary/progress/renderer
- [ ] handler 单测：委托、缺参、进度、错误

**P3 装配**
- [ ] 装配点唯一，且依赖已存在
- [ ] 动态依赖用惰性解析
- [ ] 未配置注册 `unavailable` + 可读原因
- [ ] 复用 host registry，无第二注册表

**P4 入口薄壳**
- [ ] 端点响应字段不变
- [ ] 进度/异常/终态语义不变
- [ ] 原有测试全绿（含前端与真实工作流）

**P5 可见性**
- [ ] 默认关闭（`debug` / `endpoint_only`）
- [ ] 打开条件写在文档里（需要什么输入、谁来确认）
- [ ] 两种可见性都有测试断言

---

## 附录 A：参考实现（作物识别）

| 文件 | 作用 | 提交 |
|---|---|---|
| `backend/runtime/crop_classification.py` | 单一实现：空间推理 → 判定 → provenance → 报告 | `e574615` |
| `backend/v2/tools/crop_tool.py` | spec + 输入模型 + handler + 装配函数 | `1e97b04` |
| `backend/api/canonical/router.py` | 装配 + 端点改走 `registry.invoke` | `1e97b04` |
| `backend/v2/tools/registry.py` | `invoke` 支持 `progress_callback` | `1e97b04` |
| `backend/tests/test_crop_classification_service.py` | 7 项服务测试 | `e574615` |
| `backend/tests/test_crop_tool.py` | 9 项工具/装配测试 | `1e97b04` |
| `backend/v2/middleware/` + `backend/v2/seams/` + `backend/v2/composition.py` | 管线、seam、装配清单 | `18887e0`、`35e582f` |

未打开项：模型可见性（`KTP_CROP_TOOL_MODEL_VISIBLE`，默认 `false`）；报告未转 `PackArtifactView`。

## 附录 B：与 `algorithm-tool/v1` 的关系

- 形态 A 直接使用该契约（`AlgorithmToolInput` / `AlgorithmToolResult` / 12 个冻结错误码 / provenance / 生命周期事件）。
- 形态 B **复用**其中的错误码、产物与 provenance 语义，但不强制 `AlgorithmToolInput` 形状——因为它的输入里含宿主对象，套用会逼出伪造字段。
- 升级路径：当影像准备步骤挂载后，crop 的输入从 `imagery_snapshot` 升级为 `dataset_refs`，即可从形态 B 迁移到形态 A；迁移时保留旧字段作为兼容期输入，一次性切换并加契约测试。
