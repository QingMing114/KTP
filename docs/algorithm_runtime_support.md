# CORE-201 公共算法运行支撑

状态：已实现，契约版本 `algorithm-tool/v1`。

## 1. 边界与执行链

算法工具继续复用唯一执行链：

`Submission -> BoundedRuntimeEngine -> ToolExecutor -> ToolRegistryV2 -> algorithm handler`

`ToolExecutor` 在 PolicyGuard 放行后注入 `ToolExecutionContext` 和
`RuntimeAlgorithmExecutionControl`；模型只能生成 `AlgorithmToolInput`。旧工具仍走原有
`ToolRegistryV2.invoke()`，算法工具只能走 `invoke_algorithm()`，不存在第二套调度器或执行引擎。

算法 handler 统一签名：

```python
def handler(
    tool_input: AlgorithmToolInput,
    execution_context: ToolExecutionContext,
    execution_control: AlgorithmExecutionControl,
) -> AlgorithmToolResult:
    ...
```

## 2. 公共组件

- `dataset_resolver.py`：只从 `RequestContextV2.datasets` 按 `dataset_id` 解析文件；校验
  `dataset:read`、角色、存在性、格式、媒体类型和大小，不接受模型提供的路径。
- `workspace.py`：为每次调用建立受控根目录内的独立工作区，拒绝路径逃逸，并在成功或异常时清理。
- `execution.py`：把现有取消事件和 SSE emitter 转为单调进度、协作式取消及 deadline 检查。
- `errors.py`：使用冻结错误码；非预期异常只公开异常类型，不公开原始消息、路径或堆栈。
- `artifacts.py`：工作区清理前原子复制产物，计算 SHA-256 和字节数，生成稳定 `art_*` ID 与
  产品 API URL。主机内部路径使用 Pydantic private attribute/排除字段传给 ArtifactStore，不进入响应。
- `model_runtime.py`：线程安全模型租约、引用计数和释放/驱逐；异常路径同样释放租约。
- `probe.py`：保留确定性契约探针，但已改为严格 handler 签名。

空间元数据和 provenance 由适配器按冻结契约写入 `AlgorithmArtifact.spatial` 与
`AlgorithmToolResult.provenance`，兼容桥会无损交给现有 ArtifactStore。

## 3. 超时与资源限制

deadline 从工具 Manifest 的 `runtime_requirements.timeout_seconds` 计算。Python 进程内算法通过
`raise_if_cancelled()` 协作检查并归一化为 `TIMEOUT`；用户取消沿现有 `RuntimeCancellationError`
终止整个 run。公共层不声称能强杀不合作的第三方 native 调用；真实适配器若包含不可中断调用，必须在
适配器阶段使用可终止子进程，并在 `finally` 中回收进程、模型租约、临时文件和 GPU 资源。

## 4. 已知鉴权边界

当前 `ResolvedDatasetV2` 没有 owner/tenant 字段。CORE-201 已强制“PolicyGuard 放行后的工具权限 +
本次请求注册数据集白名单”，但不能伪造细粒度所有权判断。`INT-301` 接入真实工具时必须把数据集
owner/tenant 授权结果带入可信上下文；在此之前，适配器不得绕过 canonical 数据集注册入口。

## 5. 验证

专项验证：

```powershell
cd backend
python -m pytest -q v2/tests/test_algorithm_tool_contract.py v2/tests/test_algorithm_runtime_support.py
```

覆盖契约 Schema、上下文身份、输入脱敏、数据集解析、权限不足、格式/大小、工作区路径逃逸、成功/
异常清理、进度单调性、取消、超时、产物持久化、校验和、内部路径不序列化、provenance、稳定产物 ID、
模型异常释放及通过完整 bounded runtime 的生命周期事件。
