# 遥感算法工具契约 v1

> 工作包：`STD-001`
> 契约标识：`algorithm-tool/v1`
> 状态：已冻结（2026-09-08）

## 1. 目标与边界

该契约把遥感算法实现接入现有唯一执行链：

```text
Canonical Submission
  -> BoundedRuntimeEngine
  -> Planner / PolicyGuard
  -> ToolExecutor / ToolRegistryV2
  -> algorithm-tool/v1 adapter
  -> AlgorithmToolResult
  -> ObservationV2 / PackArtifactView compatibility bridge
```

`AlgorithmToolResult` 是新算法适配器的事实输出；`ObservationV2` 和 `PackArtifactView` 只是现有运行时的单向兼容视图。禁止把 legacy 输出反向猜测成严格算法结果，也禁止新建算法专用执行引擎。

本阶段只冻结契约并提供确定性探针，不包含 KDD2020、DPA 或 MariNeXt/MADOS 的真实推理代码。

## 2. 代码位置

| 文件 | 职责 |
| --- | --- |
| `backend/v2/tools/remote_sensing/contract.py` | 输入、输出、错误、产物、provenance、进度、上下文和 Schema 校验 |
| `backend/v2/tools/remote_sensing/bridge.py` | 严格结果到现有 Runtime DTO 的单向转换 |
| `backend/v2/tools/remote_sensing/probe.py` | 不执行真实算法的确定性契约测试工具 |
| `backend/schemas/runtime.py` | 通用 ToolSpec 元数据和 Runtime 产物兼容枚举 |
| `backend/v2/tools/registry.py` | 仅对 `algorithm-tool/v1` 执行严格输入校验与可用性拦截 |
| `backend/v2/tests/test_algorithm_tool_contract.py` | 契约与统一运行时验收测试 |

后续适配器只能依赖 `remote_sensing` 契约包，不能复制这些模型。

## 3. ToolSpec 必填语义

算法工具使用 `build_algorithm_tool_spec()` 构建，并声明：

- 稳定业务能力名，例如 `remote_sensing.crop_classification`。
- `contract_version = algorithm-tool/v1`。
- Draft 2020-12 输入和输出 JSON Schema。
- `availability` 与不可用原因。
- `permissions`，至少区分数据读取和产物写入。
- `runtime_requirements`，声明设备、超时、取消和资源需求。
- `implementation`，记录算法和适配器版本。
- `produces_artifacts`、能力、上下文要求和可见范围。

旧工具默认 `contract_version = legacy`，不在本工作包中强制迁移，避免破坏现有行为。

## 4. 输入契约

大模型只能生成 `AlgorithmToolInput`：

```json
{
  "dataset_refs": [
    {
      "dataset_id": "ds_01J...",
      "role": "primary_image",
      "pair_key": "field-001",
      "media_type": "image/tiff"
    }
  ],
  "parameters": {
    "confidence_threshold": 0.7
  },
  "output_options": {
    "artifact_roles": ["mask", "statistics"],
    "formats": ["image/tiff", "application/json"],
    "include_visualization": true,
    "include_statistics": true
  }
}
```

输入 Schema 设置 `additionalProperties: false`。禁止出现本地路径、模型路径、Shell 命令、凭据或内部地址。

`ToolExecutionContext` 由 Runtime 注入，不属于模型输入，包含 execution、trace、用户/租户、会话、run、权限和 deadline。`CORE-201` 负责把现有取消事件和进度发送器实现为 `AlgorithmExecutionControl`。

## 5. 输出契约

所有适配器必须先构造并通过 `AlgorithmToolResult` 校验，再交给兼容桥：

```json
{
  "contract_version": "algorithm-tool/v1",
  "status": "succeeded",
  "summary": "分类完成，共处理 1 个样本。",
  "metrics": {"sample_count": 1},
  "predictions": {"class_id": "wheat", "confidence": 0.93},
  "artifacts": [],
  "provenance": {
    "capability_name": "remote_sensing.crop_classification",
    "tool_version": "1.0.0",
    "algorithm_name": "KDD2020",
    "algorithm_version": "pinned-commit",
    "dataset_versions": {"ds_01J...": "sha256:..."},
    "environment": {"device": "cpu"}
  },
  "validation": {"passed": true, "checks": []},
  "warnings": [],
  "runtime": {
    "execution_id": "exec_01J...",
    "trace_id": "trace_01J...",
    "started_at": "2026-09-08T03:00:00Z",
    "finished_at": "2026-09-08T03:00:01Z",
    "duration_ms": 1000,
    "device": "cpu"
  },
  "error": null
}
```

规则：

- `succeeded` 不允许携带 `error`。
- `failed`、`cancelled`、`unavailable` 必须携带结构化 `error`。
- 产物必须使用受控访问 URL、SHA-256、大小和明确媒体类型；不得返回宿主机路径。
- 空间产物补充 CRS、bbox、分辨率、宽高、波段和类别信息。
- provenance 至少能追溯能力、适配器、算法、模型、数据和参数版本。

## 6. 错误码

冻结错误码：

- `INVALID_INPUT`
- `DATASET_NOT_FOUND`
- `DATASET_FORBIDDEN`
- `UNSUPPORTED_FORMAT`
- `BAND_MISMATCH`
- `MODEL_UNAVAILABLE`
- `RESOURCE_EXHAUSTED`
- `TIMEOUT`
- `CANCELLED`
- `INFERENCE_FAILED`
- `ARTIFACT_PERSIST_FAILED`
- `CONTRACT_VERSION_MISMATCH`

适配器不得把绝对路径、凭据、内部堆栈或原始子进程命令写入 `message` 和 `detail`。

## 7. 生命周期事件、取消与清理

现有 Runtime 继续负责 `tool.started`、`tool.completed`、`artifact.available` 和 run 终态事件。算法内部进度统一表示为 `AlgorithmProgressEvent`：

- stage：`validating`、`preparing`、`running`、`persisting`、`finalizing`。
- progress：闭区间 `[0, 1]`。
- execution ID 必须与最终 Runtime 记录一致。

算法必须协作式检查 Runtime 提供的 `AlgorithmExecutionControl.raise_if_cancelled()`。临时文件、子进程、模型句柄和 GPU 资源必须在 `finally` 中清理。当前契约探针已经验证成功和受控失败两条路径的临时目录清理；真实资源生命周期在 `CORE-201` 实现。

## 8. 可用性规则

- `available`：允许进入注册表执行。
- `unavailable`：能力已定义但依赖或材料不齐，注册表必须在调用前拒绝。
- `disabled`：由配置或安全策略关闭，同样不得调用。

`unavailable` 和 `disabled` 必须说明原因。农田障碍物检测在算法、许可证、权重、数据和类别定义齐备前保持 `unavailable`，不得接入 mock handler。

## 9. Canonical 与 `/v2` 边界

- Canonical Submission 是产品入口，数据引用在边界层解析为 Runtime 上下文。
- ToolSpec 的新增字段通过现有工具清单/调试 Manifest 序列化，不建立第二套 Manifest 模型。
- `/v2` 保留现有 `ObservationV2` 和 `PackArtifactView`；兼容桥只负责投影，不改变严格结果。
- Canonical ArtifactStore 仍负责生成稳定 artifact ID 和访问地址；算法适配器不能自行暴露文件系统路径。
- `CORE-201` 实现数据引用解析、执行上下文注入、进度/取消桥、产物持久化和统一清理。
- `INT-301` 才负责三个真实工具的集中注册、allowlist、Planner、PolicyGuard 和 Canonical SSE 联调。

## 10. 验收命令

```powershell
$env:PYTHONPATH = "backend"
conda run --no-capture-output -n ktp-dev python -m pytest backend/v2/tests/test_algorithm_tool_contract.py -q
```

全量受控回归仍按 `docs/testing.md` 执行。契约、文档和全量测试均通过后，`STD-001` 才能标记为已冻结。

## 11. 冻结验证记录

2026-09-08 验证结果：

- 契约定向测试：12 passed。
- 后端受控基线：194 passed，1 个既有 Starlette/httpx deprecation warning。
- 前端测试：92 passed。
- 前端 ESLint：0 error、0 warning。
- 前端生产构建：通过。
- `pip check`：没有损坏的依赖关系。

冻结后如需更改字段语义、状态、错误码或安全边界，必须升级契约版本；只增加向后兼容的可选元数据时，也必须补 Schema 和兼容测试。
