# AUD-103 污染区域分割算法审计

## 1. 审计结论

- 审计状态：**资料与源码审计完成，真实推理 smoke 阻塞**。
- 候选实现 MariNeXt 与数据集 MADOS 在任务、输入和 15 类语义分割目标上匹配，可以继续作为 `remote_sensing.pollution_segmentation` 的候选技术路线。
- 当前不能进入 `ALG-213` 实现：本机没有 MADOS 数据、预训练权重和兼容的 PyTorch/MMCV/GDAL 环境；预训练权重虽由项目页公开下载，但没有随仓库发布，也未发现独立的权重许可证和可固定的校验和。
- 产品默认“污染区域”应只聚合 **Marine Debris（类别 1）与 Oil Spill（类别 6）**。其余类别应作为海表特征或易混淆背景分别输出。Sea snot 是否纳入产品污染统计必须由产品与领域负责人单独确认，不能由适配器自行扩大口径。
- 上游 `evaluation.py` 不可直接作为生产适配器：它依赖数据集 split 和标签，不能自然处理单个场景裁剪；其集成推理分支存在多数投票结果未被实际写出的变量使用问题，并把输出标记为非真实地理参考。`ALG-213` 必须抽取并测试独立推理封装，不能直接调用原 CLI 后宣称完成。

因此，本工作包完成的是可追溯的准入审计，而不是算法可运行证明。下文“出口条件”全部满足后，才能把 `ALG-213` 从阻塞改为就绪。

## 2. 审计范围与依据

本次只读检查了以下项目资料。用户最初给出的 `doc/` 路径在当前工作区已不存在，实际文件位于 `G:/Code/ktp_product/dev-data/`；未修改这些 Office 文件。

- `dev-data/算法自身的输入&输出.docx`
- `dev-data/整合算法工具后--大模型角度的输入&输出.docx`
- `dev-data/搜集到各任务的算法&数据集（含地址）.xlsx`
- `memory/algorithm_tools_and_rag_development_plan_2026-09-08.md`
- `docs/algorithm_tool_contract_v1.md`

外部事实只采用项目作者或数据发布方的一手来源：

- [MariNeXt 与 MADOS 官方项目页](https://marine-pollution.github.io/)
- [官方代码仓库](https://github.com/gkakogeorgiou/mados)
- [本次审计固定的源码提交 c20a7e9](https://github.com/gkakogeorgiou/mados/tree/c20a7e972bdf111126540d8e6caa45808352f138)
- [MADOS 数据集 Zenodo 记录与 DOI](https://zenodo.org/records/10664073)
- [论文 DOI：Detecting Marine Pollutants and Sea Surface Features with Deep Learning in Sentinel-2 Imagery](https://doi.org/10.1016/j.isprsjprs.2024.02.017)

## 3. 来源、版本与许可证

| 对象 | 固定依据 | 许可证结论 | 准入判断 |
| --- | --- | --- | --- |
| MariNeXt 代码 | `gkakogeorgiou/mados`，提交 `c20a7e972bdf111126540d8e6caa45808352f138` | 仓库根目录为 MIT License | 代码可修改和集成，但发行时必须保留版权和许可文本 |
| MADOS 数据 | Zenodo DOI `10.5281/zenodo.10664073`，2024-02-16 发布 | CC BY 4.0 | 可使用和改编；演示数据、派生夹具及文档必须保留署名和来源 |
| MADOS 压缩包 | `MADOS.zip`，4,038,418,740 bytes，`md5:1076b25d2797be3095d82a61105c7380` | 随 Zenodo 数据记录 | 下载后必须先校验 MD5；部署清单另记录内部 SHA-256 |
| MariNeXt 权重 | 官方 README 指向 Google Drive，说明提供 5 次训练的模型 | **未发现独立许可证、版本号、大小或校验和** | 生产集成前必须获得并归档权重许可说明、文件清单和 SHA-256 |

Zenodo 说明解压后数据约需 5.35 GB。源码仓库没有正式 release/tag，`master` 也可能继续变化，因此不能依赖浮动分支，必须固定到提交哈希。仓库内 `marinext/trained_models` 只有占位文件，克隆代码不会得到权重。

## 4. 项目资料与官方事实对照

| 项目资料描述 | 官方核对 | 处理决定 |
| --- | --- | --- |
| 数据存放于 `Scene_0` 至 `Scene_174` | 官方 Zenodo 为 174 个目录，即 `Scene_0` 至 `Scene_173` | 修正上界，禁止生成或期待 `Scene_174` |
| 每个场景下有 `10`、`20`、`30` 三个分辨率目录 | 官方结构为 `10`、`20`、`60` | 将 `30` 视为文档错误；60 m 目录含 B01 |
| 输入包含 Sentinel-2 的 11 个波段 | 与官方代码、数据说明一致 | 必须校验完整 11 波段集合、顺序和裁剪标识，不接受仅 RGB 预览图 |
| RGB PNG 只用于可视化 | 与官方说明一致 | 不进入模型张量，不得作为缺失波段时的回退 |
| `_cl` 是污染区域标注 | `_cl` 实际是 15 类稀疏语义标注，0 为未标注 | 不得把 0 当作“无污染”；评估时必须忽略 0 |
| Dogliotti 与 Nechad2016 浊度文件未用于算法 | 官方代码按 `*L2R_rhorc*` 收集模型输入，不读取 `_TUR_*` | 从模型输入中排除；可作为未来独立工具，不能静默混入 MariNeXt |
| 大模型提示直接使用 `/data/remotesensing/pollution/Scene_134` 和 crop 9 | 冻结契约禁止模型提供宿主机路径 | 产品入口改用受控 `dataset_ref` 和服务端解析的 `scene_id/crop_id` |

表格中给出的 MariNeXt/MADOS 组合是正确的；但本项目资料没有给出权重地址、许可证、依赖锁定、精确波段顺序、忽略类和统计口径，因此不能仅凭 Office 文档开工。

## 5. 原始输入与预处理契约

### 5.1 波段集合和固定顺序

MADOS 文件名使用中心波长，官方 loader 从 `10`、`20`、`60` 子目录搜集 `*L2R_rhorc*_<crop>.tif`，按文件名中的波长数值升序排序。该排序与归一化数组共同形成模型不可变输入语义：

| 张量通道 | Sentinel-2 波段 | MADOS 文件中心波长 | 原生分辨率 |
| ---: | --- | ---: | ---: |
| 0 | B01 Coastal aerosol | 443 nm | 60 m |
| 1 | B02 Blue | 492 nm | 10 m |
| 2 | B03 Green | 560 nm | 10 m |
| 3 | B04 Red | 665 nm | 10 m |
| 4 | B05 Red edge 1 | 704 nm | 20 m |
| 5 | B06 Red edge 2 | 740 nm | 20 m |
| 6 | B07 Red edge 3 | 783 nm | 20 m |
| 7 | B08 NIR | 833 nm | 10 m |
| 8 | B8A Narrow NIR | 865 nm | 20 m |
| 9 | B11 SWIR 1 | 1614 nm | 20 m |
| 10 | B12 SWIR 2 | 2202 nm | 20 m |

B09（水汽）和 B10（卷云）不在这 11 个输入波段中。适配器不能按 Sentinel-2 波段编号做普通字符串排序，因为 `B8A`、`B11`、`B12` 容易错位；应在 Manifest 中显式记录上述顺序并逐通道验证。

### 5.2 官方预处理链

1. 输入是 ACOLITE 生成的 Rayleigh-corrected reflectance，文件标识为 `L2R_rhorc`，不是任意 Sentinel-2 L1C/L2A DN 值。
2. 将 20 m 与 60 m 波段升采样到 10 m。官方 dataset loader 使用 nearest；`stack_patches.py` 支持 nearest 或 bilinear，默认 nearest。首版适配器应固定 nearest 以复现权重训练分布。
3. 每个 crop 的目标尺寸是 `240 x 240`，即 10 m 网格上的约 `2.4 x 2.4 km`。
4. NaN 按通道均值填充，再按固定均值和标准差做 z-score：

```text
mean = [0.05826760, 0.05223386, 0.04381474, 0.03570830, 0.03412902,
        0.03680401, 0.03999107, 0.03566642, 0.03965081, 0.02679930,
        0.01978944]
std  = [0.03240627, 0.03432253, 0.03548120, 0.03757690, 0.03785412,
        0.04992323, 0.05884482, 0.05545856, 0.06423746, 0.04211187,
        0.03019115]
```

5. 官方评估默认 `batch=1`、11 输入通道、15 输出通道并开启 TTA；README 还允许把 5 次训练的权重放入目录做集成。

适配器必须在输入校验中拒绝缺波段、重复波段、跨 crop 混配、尺寸不一致、无法建立 10 m 对齐网格、非 `rhorc` 且未经等价预处理的数据。对新 Sentinel-2 产品自动运行 ACOLITE 不属于 `ALG-213` 的默认范围，除非另行冻结预处理工具和版本。

## 6. 类别、忽略类与污染统计口径

MADOS `_cl` 标签的 DN 语义如下：

| DN | 类别 | 默认纳入污染聚合 |
| ---: | --- | --- |
| 0 | Non-annotated | 否；评估时忽略，不能解释成无污染 |
| 1 | Marine Debris | 是 |
| 2 | Dense Sargassum | 否 |
| 3 | Sparse Floating Algae | 否 |
| 4 | Natural Organic Material | 否 |
| 5 | Ship | 否 |
| 6 | Oil Spill | 是 |
| 7 | Marine Water | 否 |
| 8 | Sediment-Laden Water | 否 |
| 9 | Foam | 否 |
| 10 | Turbid Water | 否 |
| 11 | Shallow Water | 否 |
| 12 | Waves & Wakes | 否 |
| 13 | Oil Platform | 否；设施本身不是溢油区域 |
| 14 | Jellyfish | 否 |
| 15 | Sea snot | 待产品和领域负责人决定；首版默认否 |

论文明确把 Marine Debris 与 Oil Spill 作为两个主要污染目标。其他类别的核心作用是表达海表特征和光谱易混淆对象。仅凭“可能造成生态影响”把 Turbid Water、Oil Platform、Sea snot 等全部合并为污染，会改变论文任务定义并导致不可解释的面积结果。

冻结建议：

- 主结果保留 15 类 `uint8` 掩膜和完整图例。
- 默认派生二值污染掩膜为 `class_id in {1, 6}`。
- `pollution_pixel_count = count(class_id in {1, 6} and valid_footprint)`。
- `pollution_fraction = pollution_pixel_count / valid_prediction_pixel_count`；分母是有效推理覆盖区，不是稀疏标注像素数。
- 分别报告 Marine Debris 与 Oil Spill 的像素数、比例和面积，聚合值只是附加指标。
- 只有输出保留可信 CRS、transform 和有效像元面积时才报告平方米/公顷；否则面积指标必须省略并给出验证失败，而不是假设每像元恒为 100 平方米。
- `_conf` 是人工标注置信等级（High/Moderate/Low），不是模型概率；`_rep` 是海洋垃圾报告与标注位置关系（Very close/Away/No），也不是推理置信度。
- 模型 softmax 最大值只能命名为 `model_score` 或 `max_softmax_score`，在完成校准前不能宣称为统计置信概率。

评估时，上游 loader 先把标签减 1，原 DN 0 变成 `-1`，训练损失和评估只对 `target != -1` 的已标注像素计算。MADOS 是稀疏标注数据集，因此 F1、mIoU、OA 的分母必须注明“已标注像素”；不能与整幅预测图的覆盖比例混用。

## 7. 官方代码与运行环境审计

官方 README 建议 Python 3.8.12、GDAL 3.3.2、PyTables 3.7.0。`requirements.txt` 的核心固定版本包括：

- `torch==1.11.0+cu113`
- `torchvision==0.12.0+cu113`
- `mmcv-full==1.6.0`
- `numpy==1.23.1`
- `timm==0.4.12`
- `rasterio==1.3a3`
- `pyproj==3.3.0`
- `scikit-image==0.19.0`
- `scikit-learn==1.0.1`
- `scipy==1.8.1`
- `h5py==3.7.0`

这是一套 CUDA 11.3 和旧版 MMCV/PyTorch 技术栈。当前 `ktp-dev` 环境没有 `torch`、`torchvision`、`mmcv`、`osgeo`、`tables` 和 `pyproj`，只有 `rasterio` 可被发现，不能执行真实模型。主机有 16 GB RTX 4060 Ti，但 GPU 存在不等于依赖兼容；优先建议为算法建立固定 Linux/CUDA 容器镜像，不要污染 KTP 后端主环境。

### 7.1 必须先修复或隔离的上游问题

1. `evaluation.py` 把各权重输出加入 `all_predictions` 并计算众数，但随后评估和写图使用的是循环末次的 `predictions`，而不是 `all_predictions`。这使 5 模型投票的预期语义没有落实。
2. 掩膜写出时硬编码 `crs='+proj=latlong'`，代码注释也说明它是“non-georeferenced”；同时没有可靠传递源影像 transform。该输出不能直接作为 KTP 地图图层或面积统计依据。
3. 写出的类别掩膜沿用输入波段 dtype，而不是显式 `uint8`；产物格式和 nodata 语义不稳定。
4. 官方 CLI 通过 `_cl` 文件枚举 crop，并依赖 `splits/test_X.txt`。它是数据集评估入口，不是无标签单场景服务入口。
5. `MADOS` loader 在构造时把整个 split 的影像和标签堆入内存。按 2,803 个 11 通道 `240 x 240` float32 patch 粗略估算，仅完整影像张量就约 7 GB，尚未包含标签、Python/Numpy 副本、TTA 和模型。
6. 评估脚本会把权重目录中所有 `.pth` 模型同时加载到设备；5 个模型加 TTA 会放大显存和时延，必须有资源预算和并发限制。
7. 默认参数把 `model_path` 写成某个 `.pth` 文件，但实现用 `glob(model_path/*.pth)`，因此必须显式传权重目录；若目录为空，没有清晰的 `MODEL_UNAVAILABLE` 预检。
8. 官方实现没有 KTP 所需的进度、取消、超时、受控产物持久化、错误脱敏和 `finally` 资源清理语义。

这些问题不要求修改上游仓库；`ALG-213` 应在独立适配器中建立最小、可测试的推理封装，并保留来源和补丁说明。

## 8. Smoke 状态与复现方案

### 8.1 本次实际检查

- 已固定并逐文件审计官方源码提交 `c20a7e9`。
- 已通过 Zenodo 官方 API 核对数据包大小、MD5、CC BY 4.0、目录结构、类别映射和 split 文件。
- 已在工作区搜索 `Scene_134`、`MADOS`、`L2R_rhorc`、`model_ema.pth` 和 `trained_models`，没有找到本地数据或权重。
- 已探测 `ktp-dev` 依赖，确认真实推理所需核心模块缺失。
- 没有下载约 4 GB 的数据包，也没有从未明确授权的第三方镜像获取权重，因此没有伪造成功 smoke。

### 8.2 获得数据和权重后的上游基线命令

以下命令用于复现官方 test split，不是最终 KTP 单 crop 接口。运行前必须固定容器、核对权重许可和 SHA-256，并保证 `model_path` 指向包含 `.pth` 文件的目录：

```bash
python marinext/evaluation.py \
  --path ./data/MADOS \
  --model_path ./marinext/trained_models/1 \
  --split test \
  --batch 1 \
  --test_time_augmentations true \
  --predict_masks true \
  --gen_masks_path ./smoke-output
```

该命令会加载整个 test split。针对产品资料中的 `Scene_134` / crop `9`，还必须先确认：

1. `Scene_134` 目录确实存在。
2. crop 9 的 `_cl`、11 个 `L2R_rhorc` 波段和裁剪后缀完全匹配。
3. 该 crop 属于所选 split，或建立注明来源、合法分发的单 crop 测试夹具。
4. 上游命令输出仅用于算法对照；KTP smoke 应通过新推理封装保留真实 transform/CRS 并返回契约结果。

### 8.3 KTP 最小 smoke 验收证据

`ALG-213` 的最小 smoke 至少应证明：

- 服务端从一个受控 `dataset_ref` 解析出同一 `scene_id + crop_id` 的 11 个波段，客户端和大模型看不到本地路径。
- 预检记录波段集合、顺序、尺寸、分辨率、dtype、nodata、CRS、transform 和输入校验和。
- 使用一个固定权重和固定预处理得到 `15-class uint8 GeoTIFF`、`{1,6}` 二值污染 GeoTIFF、JSON 统计和图例。
- 输出与源 10 m 网格的 CRS、bbox、transform、宽高一致；GeoTIFF 可被重新打开并验证类别值域为 1 至 15 或明确的 nodata。
- `AlgorithmToolResult` 记录源码提交、权重 SHA-256、数据版本、参数、设备、运行时、警告和产物 SHA-256。
- 缺波段返回 `BAND_MISMATCH`，缺权重返回 `MODEL_UNAVAILABLE`，取消和超时不留下临时文件或 GPU 句柄。

## 9. 资源与安全风险

| 风险 | 影响 | 控制要求 |
| --- | --- | --- |
| 数据和派生副本占用较大 | 4 GB 压缩包、5.35 GB 解压数据，加 nearest stack 和输出后继续增长 | 使用只读数据缓存；每次任务只物化所选 crop；设置磁盘配额和清理策略 |
| loader 整体入内存 | 多并发时可能耗尽 RAM | 新封装按 crop 惰性读取，禁止构造完整 split loader |
| 5 模型和 TTA | 显存、延迟不可控 | 首版固定一个经确认的权重；集成和 TTA 作为显式参数并设置并发上限 |
| 旧 CUDA/MMCV 依赖 | 难以在主后端环境安装和维护 | 独立容器、固定镜像摘要、启动健康检查；不可用时返回 `MODEL_UNAVAILABLE` |
| 权重许可证和完整性不明 | 发布、再分发和供应链风险 | 法务/项目负责人确认授权；内部对象存储保存文件清单、来源、SHA-256 和扫描结果 |
| 稀疏标注被误读 | 指标和污染面积被夸大或混淆 | 评估分母注明“已标注像素”；推理覆盖统计与数据集评估分开 |
| 上游输出无真实地理参考 | 地图错位和面积错误 | 以受控的 10 m 参考波段复制 CRS/transform/bbox，并做 raster round-trip 测试 |
| 路径型 CLI | 违反 `algorithm-tool/v1` 安全边界 | 仅由服务端 dataset resolver 解析路径；日志和结果不得包含宿主机绝对路径 |

## 10. 对 `algorithm-tool/v1` 的适配建议

- 稳定能力名：`remote_sensing.pollution_segmentation`。
- `dataset_refs`：一个受控 MADOS crop bundle 或等价预处理后的 Sentinel-2 bundle；角色建议为 `multispectral_scene`，`pair_key` 固定为服务端规范化的 `scene_id:crop_id`。
- 用户参数只允许任务语义参数，例如 `scene_id`、`crop_id`、是否生成 TTA、污染聚合集和产物选项；权重路径、命令和内部存储地址不得进入模型输入。
- 首版固定 `resampling=nearest`、11 波段顺序、上述 mean/std、单个权重版本；任何改变都写入 provenance 并视为模型实现版本变化。
- `predictions` 至少包含 15 类像素统计、Marine Debris/Oil Spill 分项与聚合统计；`metrics` 明确单位和分母。
- `artifacts` 至少包含 15 类 mask、污染二值 mask、图例/统计 JSON；可选 RGB 预览。所有 URL 由 ArtifactStore 生成。
- `validation` 必须包含 band order、spatial alignment、CRS、nodata、class range、artifact round-trip 和统计一致性检查。
- 无许可权重、缺波段、缺真实 CRS 或推理环境不健康时必须明确失败或 unavailable，禁止用 RGB、随机 mask 或历史结果回退。

## 11. `ALG-213` 出口条件

以下条件全部完成后，本审计才允许将 `ALG-213` 标记为就绪：

- [ ] 代码固定为已审计提交或经重新审计的新提交，并保存 MIT notice。
- [ ] 取得至少一个官方权重，确认使用/再分发权限，记录来源、文件名、大小和 SHA-256。
- [ ] MADOS v1 下载并通过官方 MD5；内部保存数据版本、CC BY 4.0 attribution 和 SHA-256。
- [ ] 选定合法的小型 smoke crop；确认 `Scene_134` / crop 9 是否真实存在、文件后缀、11 波段完整性及 split 归属。
- [ ] 产品和领域负责人签字确认污染聚合集：首版建议 `{Marine Debris, Oil Spill}`，并明确 Sea snot 是否单独展示或纳入聚合。
- [ ] 固定独立算法容器、镜像摘要、CPU/GPU 最低要求、超时、显存/RAM/磁盘预算和并发上限。
- [ ] 修复或绕开上游集成投票变量错误，并用单模型/多模型测试证明实际使用的预测张量。
- [ ] 新推理封装不依赖 `_cl` 和 split 来发现输入，支持无标签单 crop，且不整体加载数据集。
- [ ] GeoTIFF 保留真实 CRS/transform，使用 `uint8` 与明确 nodata，地图 round-trip 和面积统计测试通过。
- [ ] 完成一次真实、可复现的单 crop smoke，并产出符合 `algorithm-tool/v1` 的结果、日志、校验和与清理证据。

在这些条件完成前，建议工具 Manifest 状态保持 `unavailable`，原因明确写为“模型权重、合法 smoke 数据和固定运行环境尚未完成准入”。
