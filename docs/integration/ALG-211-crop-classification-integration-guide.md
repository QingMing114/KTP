# ALG-211 作物分类接入手册

> 能力名：`remote_sensing.crop_classification`
>
> 候选算法：KDD2020 Multi Modal Crop Classification
>
> 契约：`algorithm-tool/v1`
>
> 当前准入状态：**阻塞，不得开始生产适配器编码或注册为 available**

## 1. 文档用途与开工门禁

本文是分配给 `ALG-211` 开发人员的实施规范。公共接入边界以
[`algorithm_tool_contract_v1.md`](../algorithm_tool_contract_v1.md) 和
[`algorithm_runtime_support.md`](../algorithm_runtime_support.md) 为准；算法事实与风险证据见
[`AUD-101-crop-classification.md`](../audits/AUD-101-crop-classification.md)。三者冲突时，冻结契约优先，
未经评审不得自行扩大输入、输出或回退语义。

开始编码前必须同时取得：

- KDD2020 源码固定提交 `4066b924558aa5b42ff619f7ecca79673c35a06f`。
- 与该提交、网络结构和六类映射匹配的 `.h5` 权重，包含来源、许可、文件大小和 SHA-256。
- 一对可合法用于开发和 CI 的 RGB JPG 与 23 步 NDVI CSV，包含来源、许可、SHA-256 和期望标签。
- 经验证可复现上游结果的隔离 TensorFlow/Keras 运行环境及镜像摘要。
- 模型负责人签字确认网络名、训练配置、类别顺序、输入归一化和期望输出容差。

任何一项缺失时，允许补充审计材料和环境探针，不允许生成随机权重、合成预测、规则分类或 mock
结果并声称真实 smoke 通过。ToolSpec 必须保持 `unavailable`。

## 2. 已冻结的算法身份

| 字段 | 固定值 |
| --- | --- |
| capability | `remote_sensing.crop_classification` |
| source repository | `https://github.com/kkgadiraju/multi-modal-crop-classification` |
| source commit | `4066b924558aa5b42ff619f7ecca79673c35a06f` |
| source license | MIT；仅覆盖源码 |
| candidate branch | `concatenation` |
| image input | RGB JPEG，适配到 `224 x 224` |
| temporal input | CSV 中大小写精确的 `NDVI` 列，固定 23 步 |
| output | 六类概率、top-1 类别和 confidence |

稳定类别表不得按目录扫描或字典顺序重建：

| class_id | key | 中文名 |
| ---: | --- | --- |
| 0 | `corn` | 玉米 |
| 1 | `cotton` | 棉花 |
| 2 | `soy` | 大豆 |
| 3 | `spring_wheat` | 春小麦 |
| 4 | `winter_wheat` | 冬小麦 |
| 5 | `barley` | 大麦 |

## 3. 代码边界与建议落点

适配器工作包只允许新增或修改算法私有目录和对应测试，建议落点：

```text
backend/v2/tools/remote_sensing/adapters/
  crop_classification.py
backend/v2/tests/
  test_crop_classification_adapter.py
tests/fixtures/remote_sensing/crop_classification/
  fixture-manifest.json
```

不要在 `ALG-211` 中修改 `ToolRegistryV2`、Canonical Router、Planner、PolicyGuard、
`BoundedRuntimeEngine`、执行器 allowlist 或前端。集中注册和公开入口由 `INT-301` 完成。不要复制
CORE-201 组件形成另一套 resolver、workspace、artifact store、线程池或执行引擎。

handler 必须使用严格签名：

```python
def run_crop_classification(
    tool_input: AlgorithmToolInput,
    execution_context: ToolExecutionContext,
    execution_control: AlgorithmExecutionControl,
) -> AlgorithmToolResult:
    ...
```

实际实现建议使用 factory 注入公共服务，避免模块级隐藏路径或在每次调用重新创建模型缓存：

```python
def build_crop_classification_handler(*, artifact_manager, model_runtime, model_catalog):
    resolver = AlgorithmDatasetResolver()

    def handler(tool_input, execution_context, execution_control):
        # resolve -> validate -> workspace -> model lease -> infer -> persist -> result
        ...

    return handler
```

`model_catalog` 只能返回已经批准的模型 ID、受控内部位置、版本和 SHA-256；测试中可注入临时目录下的
固定模型，生产中由 `INT-301` 注入真实注册服务。handler 不得从 parameters 或环境变量拼接权重路径。

## 4. 统一输入映射

一次样本必须恰好包含两个受控数据引用：

```json
{
  "dataset_refs": [
    {
      "dataset_id": "ds_image_<id>",
      "role": "primary_image",
      "pair_key": "field-001",
      "media_type": "image/jpeg"
    },
    {
      "dataset_id": "ds_ndvi_<id>",
      "role": "ndvi_timeseries",
      "pair_key": "field-001",
      "media_type": "text/csv"
    }
  ],
  "parameters": {},
  "output_options": {
    "artifact_roles": ["classification_report"],
    "formats": ["application/json"],
    "include_visualization": false,
    "include_statistics": true
  }
}
```

模型输入中禁止出现本地路径、权重路径、命令、凭据或下载地址。开发人员应调用
`AlgorithmDatasetResolver.resolve()`，设置：

- `required_roles={"primary_image", "ndvi_timeseries"}`；
- 图像后缀 `{.jpg, .jpeg}`，媒体类型 `image/jpeg`；
- 时序后缀 `.csv`，媒体类型只接受数据注册表批准的 CSV 类型；
- 每个文件和总输入大小使用 Manifest 批准的上限。

resolver 返回后还必须由适配器验证：

1. 两个引用数量各为 1，`pair_key` 非空且完全相同。
2. 文件真实签名与扩展名一致；JPEG 能由 Pillow 解码，转换后为三通道 RGB。
3. CSV 非空、编码可解析、有且仅有一个 `NDVI` 列，禁止重复表头。
4. NDVI 按数据生产方确认的顺序恰好 23 行；若包含日期/序号，必须严格单调且不得重复。
5. NDVI 可转为有限浮点数；缺失值处理首版复现上游相邻值线性插值，但首尾缺失、全 NaN 或插值后非有限值必须失败。
6. 图像缩放、`/255` 和逐样本 `StandardScaler().fit_transform()` 首版保持上游行为；任何改动提升实现版本并重新做等价性测试。

## 5. 标准执行顺序

适配器必须按以下顺序组织，并在每个长耗时边界调用 `raise_if_cancelled()`：

1. 发出 `validating` 进度，解析并校验两份数据。
2. 进入 `AlgorithmWorkspace`，发出 `preparing` 进度，生成只供本次调用使用的受控中间文件。
3. 通过 `ModelRuntimeManager.lease()` 按模型版本取得模型；loader 只从服务端模型注册配置解析权重。
4. 发出 `running` 进度，完成预处理与真实推理；不要调用上游 `sys.exit()` 型批处理入口。
5. 校验 softmax 形状为 6、所有值有限、每项位于 `[0,1]`，概率和在批准容差内为 1。
6. 发出 `persisting` 进度，用 `AlgorithmArtifactManager.persist()` 保存报告。
7. 发出 `finalizing` 进度，构造并返回 `AlgorithmToolResult`。
8. 所有异常、取消和超时路径通过 context manager/`finally` 释放模型租约、文件句柄和工作区。

公共 deadline 是协作式的；如果 TensorFlow 调用本身不可中断，必须放入可终止的隔离子进程，超时后终止并回收该进程。禁止仅在推理前后检查一次便宣称支持超时。

## 6. 输出规范

`predictions` 至少包含：

```json
{
  "top1": {
    "class_id": 0,
    "class_key": "corn",
    "display_name": "玉米",
    "score": 0.91
  },
  "probabilities": [
    {"class_id": 0, "class_key": "corn", "score": 0.91}
  ]
}
```

其中 `probabilities` 必须完整包含六类并按 `class_id` 排序。未经校准验证，字段名称使用 `score`，
不能宣称为统计意义上的置信概率。`metrics` 可包含 `class_count=6`、输入步数、推理耗时，但不得填写
未经真实评测的准确率。

至少生成一个 `classification_result` JSON 产物，内容包括六类概率、top-1、输入数据 ID、验证结果和
警告。禁止在 JSON、文件名、summary、warning 或 provenance 中写宿主机路径。

`AlgorithmProvenance` 必须记录：

- capability、工具版本、算法名与源码 commit；
- 模型名、模型版本、权重 SHA-256；
- 两个 dataset ID 对应的数据版本；
- 参数摘要校验和；
- 容器镜像摘要、Python、TensorFlow、Keras、device；
- 类别映射版本和预处理版本。

## 7. 错误码映射

| 条件 | 错误码 |
| --- | --- |
| dataset ID 未注册或文件不存在 | `DATASET_NOT_FOUND` |
| 无 `dataset:read` | `DATASET_FORBIDDEN` |
| 不是可解码 JPEG/CSV | `UNSUPPORTED_FORMAT` |
| 两个角色、pair_key、23 步或张量形状不符合 | `INVALID_INPUT` |
| 权重缺失、摘要不符、模型与类别版本不匹配 | `MODEL_UNAVAILABLE` |
| 内存、显存或输入大小超限 | `RESOURCE_EXHAUSTED` |
| deadline 到期 | `TIMEOUT` |
| 用户取消 | `CANCELLED`，由现有运行时取消整次 run |
| 模型执行或输出校验失败 | `INFERENCE_FAILED` |
| 报告复制、校验和或登记失败 | `ARTIFACT_PERSIST_FAILED` |

对外错误不得包含原始异常消息中的路径、栈、SQL、命令或凭据。

## 8. 自动化测试矩阵

`test_crop_classification_adapter.py` 至少覆盖：

- 合法 JPG + 23 步 CSV 得到固定六类向量和预期 top-1；重复运行结果在容差内一致。
- dataset ID 缺失、权限缺失、角色重复/缺失、pair_key 不一致。
- 假 JPEG、错误媒体类型、损坏图片、非 RGB 可转换输入。
- 缺 `NDVI`、重复列、22/24 步、乱序/重复日期、非数值、Inf、全 NaN 和首尾无法插值。
- 权重缺失、SHA-256 不符、类别头不是 6、模型输出 NaN 或概率不守恒。
- 进度单调并覆盖五个阶段；取消和超时后子进程、模型引用及工作区均释放。
- 报告 checksum、size、稳定 URL、provenance 完整；序列化结果不含内部路径。
- handler 通过公共 `invoke_algorithm()` contract test；旧工具测试不回退。

测试夹具必须可合法进入仓库或 CI 对象存储；仅提交 `fixture-manifest.json` 时，其中应记录来源、许可、
数据/权重 SHA-256、期望结果、容差和获取方式，不能把开发者本机路径写入清单。

## 9. 真实 smoke 步骤

1. 在隔离环境先对固定样例运行上游 `concatenation/predict_multi.py`，归档日志和输出。
2. 对完全相同的图像、CSV 和权重运行新 handler，不经过 Planner，也不注册公开工具。
3. 比较预处理张量摘要、六类概率、top-1 与上游结果；容差由模型负责人书面批准。
4. 再通过测试用 `ToolRegistryV2.register()` 和 `BoundedRuntimeEngine.stream()` 调用，验证事件、取消和产物。
5. 归档源码 commit、镜像摘要、权重/输入/输出 SHA-256、耗时、峰值内存和设备信息。

建议未来提供的 smoke 入口（该模块在实现前不存在）：

```powershell
conda run -n <locked-env> python -m v2.tools.remote_sensing.adapters.crop_classification_smoke `
  --fixture-manifest <controlled-manifest>
```

smoke 只有在真实模型运行、期望结果比对、资源清理和契约校验全部通过时才算成功。

## 10. 交付与评审清单

- [ ] 审计阻断项全部关闭，AUD-101 状态更新为通过。
- [ ] 适配器只依赖公共 contract/runtime support，没有第二套执行链。
- [ ] 输入不接受路径，模型和数据均由可信注册信息解析。
- [ ] 六类、23 步和预处理行为已版本化并由真实 smoke 验证。
- [ ] 所有成功/失败/取消/超时路径无资源泄漏。
- [ ] 自动化测试、fixture manifest、真实 smoke 记录和复现命令齐全。
- [ ] ToolSpec 仍未在适配器工作包中集中注册；交由 `INT-301`。

全部勾选后，提交信息使用 `feat(ALG-211): add crop classification adapter`，再交给独立评审者复跑，
不得由适配器作者自行把能力改为 `available`。
