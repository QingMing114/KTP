# ALG-214 农田障碍物检测接入手册

> 能力名：`remote_sensing.farmland_obstacle_detection`
>
> 候选数据集与数据使用软件：FieldSAFE
>
> 候选检测算法：**尚未选定；FieldSAFE 不是预训练检测算法**
>
> 契约：`algorithm-tool/v1`
>
> 当前准入状态：**阻塞，不得开始生产适配器编码或注册为 `available`**

## 1. 文档用途与开工门禁

本文是 `ALG-214` 的接入规范。公共边界以
[`algorithm_tool_contract_v1.md`](../algorithm_tool_contract_v1.md) 和
[`algorithm_runtime_support.md`](../algorithm_runtime_support.md) 为准；项目当前对该能力的基线决策见
[`base_001_baseline.md`](../base_001_baseline.md)。三者冲突时，冻结契约优先。

FieldSAFE 是农业场景的多传感器数据集，提供 ROS 使用软件、传感器数据和障碍物位置标注；它**没有定义一套可
直接接入 KTP 的、带权重的障碍物检测模型**。因此不得把 `mikkelkh/FieldSAFE` 的 ROS 回放/demo 代码包装为
“障碍物检测算法”。

开始生产编码前，必须同时具备：

- 选定的检测算法仓库、不可变 commit/tag、源码许可证与许可证负责人书面结论。
- 可部署的推理入口；明确模型架构、输入模态、预处理、后处理和 CPU/GPU/容器依赖锁。
- 与固定模型匹配的合法权重，记录来源、使用/再分发许可、文件名、大小和 SHA-256。
- FieldSAFE 或其他已批准数据集的使用授权；FieldSAFE 当前公开许可为 `CC BY-NC-SA 4.0`，未取得额外授权时不得
  用于商业产品、可分发 CI fixture 或生产演示。
- 至少一个可合法用于开发与 smoke 的小型样例，包括原始传感器数据、标注、时间同步/标定文件、SHA-256 和期望结果。
- 产品、领域和安全负责人共同批准：输入传感器范围、障碍物类别表、忽略类、最小目标尺寸、告警阈值与失败策略。
- 经验证的坐标系转换、传感器外参和目标输出坐标系；若输出地理位置，还必须明确 GNSS/IMU/时间同步语义。
- 固定环境镜像摘要、显存/内存/磁盘基线、最大并发和取消/超时清理策略。

任一项缺失时，仅允许补充审计资料、环境探针和不可用状态；禁止使用通用 COCO 权重、随机框、历史检测结果、
规则阈值或 mock 输出冒充 FieldSAFE 真实检测通过。ToolSpec 必须保持 `availability = unavailable`。

## 2. 已确认的数据集身份与未知项

| 字段 | 已确认值或约束 |
| --- | --- |
| capability | `remote_sensing.farmland_obstacle_detection` |
| dataset | FieldSAFE — Dataset for Obstacle Detection in Agriculture |
| 发布机构 | Aarhus University |
| 官方数据页 | `https://vision.eng.au.dk/fieldsafe/` |
| 数据使用仓库 | `https://github.com/mikkelkh/FieldSAFE` |
| 数据使用形式 | ROS bags；官方仓库含 ROS 示例与静态/动态障碍物 GPS ground truth |
| 采集场景 | 2016 年 10 月，丹麦草场割草，拖拉机平台约 2 小时记录 |
| 已知模态 | 立体相机、热成像、Web 相机、360 相机、LiDAR、雷达、IMU/GNSS |
| 已知障碍物 | 人、人体模型、石块、桶、建筑、车辆、植被等静态或动态目标 |
| 标注 | 障碍物对象标注与地理坐标；其与某一相机帧/传感器时间戳的可用对应关系必须通过小样例验证 |
| 数据许可 | FieldSAFE 官方页声明 `CC BY-NC-SA 4.0`；非商业限制在产品准入前必须处理 |
| 算法仓库/权重 | **未知；不得从数据集仓库推断** |

`FieldSAFE` 仓库是数据读取、标定/坐标处理和 ROS demo 的来源，不是模型来源。若未来选用某一检测模型，必须新增
审计记录，至少冻结：算法仓库、commit、代码许可、权重许可、训练数据、类别表和精度/延迟基线。不得使用浮动的
`main`/`master` 分支作为 provenance。

## 3. 产品范围必须先收窄

FieldSAFE 是多模态机器人数据集；KTP 的首版不能笼统承诺“所有模态农业障碍物检测”。在选定模型前，应由产品
负责人从下列互斥方案中批准一个首版 profile：

| profile | 合法的首版输入 | 典型输出 | 额外风险 |
| --- | --- | --- | --- |
| `rgb_camera_v1` | 经标定、时间同步的单帧 Web/RGB 相机图像 | 2D 检测框、类别、score | 不能从 2D 框虚构距离或地理位置 |
| `stereo_camera_v1` | 同步的左右立体帧与批准标定 | 2D 框，可选可信深度/距离 | 左右帧对齐、深度误差和时间同步 |
| `lidar_v1` | 已批准格式的单时刻点云 | 3D 框或障碍物簇 | 地面分割、坐标系、稀疏目标 |
| `fusion_v1` | 明确列出的相机/LiDAR/雷达同步 bundle | 检测框与融合定位 | 标定、外参、时钟和故障降级 |

首版建议优先选择 `rgb_camera_v1` 或 `stereo_camera_v1`，先闭环数据集解析、检测、Artifact、审计和告警语义；
融合模型必须作为独立能力/profile 审计，不能在参数中临时拼接传感器文件。

产品分类表也必须冻结。FieldSAFE 文本列举的对象是数据集事实，不等同于最终模型的类别。首版至少要明确：

- `class_id`、稳定 `class_key`、中文显示名和版本；
- 哪些对象为可检测障碍物，哪些仅作背景/忽略；
- 人、车辆、石块、桶、植被、建筑和人体模型是否分别输出或聚合；
- 最小像素/尺寸、遮挡规则和 `unknown`/`other` 语义；
- `score` 的定义。未经校准，不得称为“碰撞概率”或安全等级。

## 4. 代码边界与建议落点

适配器工作包只允许改动算法私有目录、测试与受控配置，建议落点：

```text
backend/v2/tools/remote_sensing/adapters/
  farmland_obstacle_detection.py
backend/v2/tests/
  test_farmland_obstacle_detection_adapter.py
tests/fixtures/remote_sensing/farmland_obstacle_detection/
  fixture-manifest.json
  approved-obstacle-profile.json
  approved-obstacle-taxonomy.json
```

handler 必须使用严格签名：

```python
def run_farmland_obstacle_detection(
    tool_input: AlgorithmToolInput,
    execution_context: ToolExecutionContext,
    execution_control: AlgorithmExecutionControl,
) -> AlgorithmToolResult:
    ...
```

推荐通过 factory 注入 `AlgorithmArtifactManager`、`ModelRuntimeManager`、可信模型目录和 profile/taxonomy
目录。handler 只执行：

```text
resolve → validate → workspace → model lease → infer → persist → result
```

禁止从 `parameters`、文件名、环境变量、ROS bag 内的任意 URI 或客户端请求中解析权重路径、命令、凭据或内部
服务地址。

`ALG-214` 不得修改 `ToolRegistryV2`、Canonical Router、Planner、PolicyGuard、`BoundedRuntimeEngine`、
执行器 allowlist 或前端。集中注册、Planner 提示、权限、Manifest 和产品联调由 `INT-301` 完成。不得复制
DatasetResolver、workspace、ArtifactStore 或新建第二套 ROS/任务执行引擎。

## 5. 统一输入契约

在产品负责人冻结 profile 前，不得实现公开 handler。以批准的 `rgb_camera_v1` 为例，输入只能引用已注册的数据：

```json
{
  "dataset_refs": [{
    "dataset_id": "ds_fieldsafe_rgb_frame_<id>",
    "role": "primary_image",
    "pair_key": "fieldsafe:session-01:timestamp",
    "media_type": "image/jpeg"
  }],
  "parameters": {
    "profile": "rgb_camera_v1",
    "taxonomy_version": "fieldsafe-obstacle-v1",
    "score_threshold": 0.5
  },
  "output_options": {
    "artifact_roles": ["detections", "preview", "statistics"],
    "formats": ["application/json", "image/png"],
    "include_visualization": true,
    "include_statistics": true
  }
}
```

对于 `stereo_camera_v1`，必须恰好包含 `left_image`、`right_image` 和服务端批准的标定引用，且使用相同
`pair_key`。对于 LiDAR 或融合 profile，必须采用单个受控 bundle Dataset；bundle manifest 由服务端注册表解析，
内部相对路径必须经过根目录包含性检查，禁止绝对路径、`..` 和链接逃逸。

`AlgorithmDatasetResolver.resolve(tool_input, execution_context, ...)` 必须负责 dataset ID、`dataset:read`、角色、
媒体类型、文件存在性和大小上限；适配器还必须验证：

1. profile、taxonomy、模型版本和参数均来自批准的服务端 catalog，用户输入只能选择，不得覆盖其内容。
2. 图像/点云真实文件签名、尺寸、编码和传感器 profile 一致；损坏文件必须拒绝。
3. `pair_key`、传感器时间戳、标定版本与外参对立体/融合 profile 一致；不满足时拒绝而非“最近邻猜配”。
4. 输入不包含未经批准的 ROS topic、额外传感器、标签文件或未来时刻数据，避免数据泄漏。
5. 面向离线 FieldSAFE 验证时，ground truth 只能用于评测，**不得**作为模型推理输入。

## 6. 标准执行流程

1. `validating`：解析 Dataset、profile、taxonomy 和模型；检查权限、文件签名、时间戳、标定与大小限制。
2. `preparing`：进入 `AlgorithmWorkspace`，按已批准 profile 做解码、去畸变、缩放、归一化和必要的坐标变换；
   每个批次调用 `raise_if_cancelled()`。
3. 通过 `ModelRuntimeManager.lease()` 获取固定模型。模型 loader 只能由服务端 catalog 提供权重与版本。
4. `running`：执行真实推理和后处理；校验所有框/掩膜/3D 几何为有限数，类别在 taxonomy 内，score 位于 `[0, 1]`。
5. 对检测框执行批准的阈值和 NMS；阈值、NMS、预处理和模型输入尺寸必须写入 profile 与 provenance。
6. `persisting`：生成结构化 detections JSON、可选可视化预览和统计；通过 `AlgorithmArtifactManager.persist()` 持久化。
7. `finalizing`：构造 `AlgorithmToolResult`，并在 `finally` 中释放模型租约、ROS readers、点云/图像 buffers、
   GPU 张量、子进程和工作区。

如果选定算法包含不可协作取消的 CUDA/native 调用，必须运行在可终止的隔离子进程或容器中；只在推理前后检查
取消标志，不能宣称支持取消/超时。

## 7. 输出、空间语义与 Artifact

`predictions` 至少应包含：

```json
{
  "profile": "rgb_camera_v1",
  "taxonomy_version": "fieldsafe-obstacle-v1",
  "detection_count": 1,
  "detections": [{
    "detection_id": "det_0001",
    "class_id": 1,
    "class_key": "person",
    "score": 0.91,
    "bbox_xyxy": [120.0, 80.0, 265.0, 460.0]
  }]
}
```

规则：

- 2D profile 仅输出像素坐标；不得从图像名、GPS 近似值或未验证标定虚构深度、距离、世界坐标或地理坐标。
- 立体/LiDAR/融合 profile 如输出距离、车体坐标或地理坐标，必须记录 frame、时间戳、标定/外参版本、坐标变换
  链和有效性检查；无法验证时省略该字段并给出 warning。
- `metrics` 可包含输入帧数、耗时、类别计数、有效检测数量；没有批准评测协议时不得填写 mAP、召回率、漏检率或
  安全等级。
- score 未经概率校准时只称 `score`，不得表述为真实世界碰撞概率。

最低 Artifact：

| role | runtime_kind | media_type | 内容 |
| --- | --- | --- | --- |
| `detections` | `classification_result` | `application/json` | 检测框/几何、类别、score、输入 ID、验证与 warning |
| `preview` | `segmentation_preview` 或 `visualization_card` | `image/png` | 可选标注预览，不替代结构化结果 |
| `statistics` | `statistics_table` | `application/json` | 类别计数、阈值、模型/profile/taxonomy 摘要 |

Artifact URL、SHA-256、大小和内部路径隔离均由公共 Artifact 层完成。对外响应、JSON、文件名、summary、warning、
错误和 provenance 中不得暴露宿主机路径、ROS bag 路径、权重路径、命令、凭据或内部网络地址。

`AlgorithmProvenance` 至少记录：能力名、adapter 版本、算法仓库与 commit、权重 ID/SHA-256、模型输入 profile、
taxonomy 版本、预处理/NMS/阈值、Dataset 版本、FieldSAFE attribution（若使用）、容器镜像摘要、Python/框架/CUDA/
device 和参数摘要。

## 8. 错误码映射

| 条件 | 错误码 |
| --- | --- |
| dataset 未注册、文件/bundle 成员缺失 | `DATASET_NOT_FOUND` |
| 无 `dataset:read` 或 profile 不允许该数据 | `DATASET_FORBIDDEN` |
| 非支持图像/点云/ROS 数据、损坏文件 | `UNSUPPORTED_FORMAT` |
| 角色、pair_key、时间戳、标定、传感器组合或输入形状不符合 | `INVALID_INPUT` |
| 融合 profile 的帧/外参/坐标系不一致 | `BAND_MISMATCH` |
| 权重缺失、摘要不符、环境/设备不健康 | `MODEL_UNAVAILABLE` |
| RAM、VRAM、磁盘或队列上限超出 | `RESOURCE_EXHAUSTED` |
| deadline 到期 | `TIMEOUT` |
| 用户取消 | `CANCELLED` |
| 推理、后处理或几何校验失败 | `INFERENCE_FAILED` |
| Artifact 复制、校验和或登记失败 | `ARTIFACT_PERSIST_FAILED` |

对外错误必须经统一错误归一化，不得暴露底层 ROS、驱动、CUDA、文件系统或容器的原始异常文本。

## 9. 自动化测试矩阵

`test_farmland_obstacle_detection_adapter.py` 至少覆盖：

- 已批准的小样例和固定模型得到确定检测结果；重复运行在批准容差内一致。
- dataset 缺失、权限不足、重复/缺失角色、错误 profile/taxonomy/模型版本。
- 损坏图像/点云、错误媒体类型、超出大小限制、无效数值与不匹配的传感器 profile。
- stereo/fusion 的时间戳、pair_key、内外参、坐标系不一致；不得静默降级为单目或最近帧。
- 无效 bbox、框越界、NaN/Inf、未知类别、score 越界、NMS 与阈值的边界行为。
- 仅在批准的标定可用时输出距离/3D/地理位置；2D profile 不得生成这些字段。
- 进度单调并覆盖五个阶段；成功、失败、取消、超时/OOM 后 workspace、模型租约、进程和 GPU 资源释放。
- Artifact checksum、大小、稳定 URL、provenance、FieldSAFE attribution（若适用）；序列化不含内部路径。
- 通过公共 `invoke_algorithm()` 和 `BoundedRuntimeEngine` 的集成测试，旧工具无回退。

测试夹具必须附 `fixture-manifest.json`，记录数据/模型来源、许可、SHA-256、传感器 profile、标定版本、预期输出
和容差。FieldSAFE 的 NC 限制未处理前，禁止把其原始帧、rosbag 或派生 fixture 提交进公开仓库、公开 CI 或产品包。

## 10. 真实 smoke 与验收

在开工门禁关闭后，按顺序完成：

1. 在锁定环境/容器中对批准的算法仓库、固定 commit、固定权重和合法小样例运行上游推理，归档原始输出。
2. 用完全相同的输入运行 KTP 候选 handler；对模型输入摘要、检测结果、类别、score 与可比较的几何输出做容差对比。
3. 验证 KTP 不把 FieldSAFE ground truth 喂给推理；ground truth 只用于离线评测并记录评测脚本版本。
4. 通过 `ToolRegistryV2.register()`、`invoke_algorithm()` 和 `BoundedRuntimeEngine.stream()` 验证权限、事件、取消、
   Artifact 与错误脱敏。
5. 归档算法源码 commit、镜像、权重、输入、标定、输出 SHA-256，资源峰值、设备、时延、取消/超时清理和许可结论。

建议未来 smoke 入口（实现前不存在）：

```powershell
conda run -n <locked-env> python -m v2.tools.remote_sensing.adapters.farmland_obstacle_detection_smoke `
  --fixture-manifest <controlled-manifest>
```

只有真实模型、期望结果比对、契约校验、Artifact 验证、资源清理和独立复跑全部通过，才可声明 smoke 成功。

## 11. 交付与评审清单

- [ ] 已选定算法及不可变版本，许可证、权重和环境准入均已关闭。
- [ ] FieldSAFE 或替代数据的使用与分发许可已由负责人确认；NC 边界有书面结论。
- [ ] 产品 profile、类别表、忽略类、最小尺寸、告警/失败语义已批准并版本化。
- [ ] 输入仅使用可信 Dataset 解析，模型不接收路径、命令或自行声明的权限。
- [ ] 传感器时间同步、标定、坐标系和可输出的空间语义已经真实验证。
- [ ] 不将 ground truth 当推理输入；不把 2D 结果伪装为距离或地理坐标。
- [ ] 成功、失败、OOM、取消和超时路径无资源泄漏。
- [ ] 自动化测试、合法 fixture、真实 smoke、provenance 与复现命令齐全。
- [ ] 适配器工作包未修改共享 Registry、Router、Planner、执行器 allowlist 或前端；统一交由 `INT-301`。

全部通过后，建议提交：

```text
feat(ALG-214): add farmland obstacle detection adapter
```

适配器作者不得自行将能力改为 `available`；必须由独立验收人和集成负责人完成复跑、合规确认与 `INT-301` 集中接入。

## 12. Git 交付方式

开发人员从最新 `origin/main` 创建独立分支：

```text
feat/ALG-214-farmland-obstacle-detection
```

通过 Pull Request 交付，禁止直接推送或合并 `main`。PR 标题使用：

```text
[ALG-214] 接入农田障碍物检测适配器
```

PR 必须包含：

- 适配器代码、自动化测试、fixture manifest、批准的 profile/taxonomy 与环境配置；
- 分支名、最终 commit SHA、实际测试命令与结果；
- 真实 smoke、同步/标定/坐标验证、取消/超时清理与资源基线证据；
- 算法、模型、数据、标定、输入和输出的 SHA-256，以及许可证/归属结论；
- 明确声明未修改 Registry、Router、Planner、执行引擎、allowlist 和前端。

权重、FieldSAFE 原始数据、rosbag、标定文件、容器镜像和大体积输出不得直接提交 Git；它们进入获批的数据、模型或
镜像存储，Git 仅保存版本、授权信息、受控引用和校验和。独立评审通过后由集成负责人合并；适配器作者不得自行合并或
执行 `INT-301` 注册。
