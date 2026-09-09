# ALG-213 污染区域分割接入手册

> 能力名：`remote_sensing.pollution_segmentation`
>
> 候选算法：MariNeXt / MADOS
>
> 契约：`algorithm-tool/v1`
>
> 当前准入状态：**阻塞，不得开始生产适配器编码或注册为 available**

## 1. 文档用途与开工门禁

公共边界见 [`algorithm_tool_contract_v1.md`](../algorithm_tool_contract_v1.md) 和
[`algorithm_runtime_support.md`](../algorithm_runtime_support.md)，审计证据见
[`AUD-103-pollution-segmentation.md`](../audits/AUD-103-pollution-segmentation.md)。

开工前必须具备：

- MariNeXt/MADOS 代码固定提交 `c20a7e972bdf111126540d8e6caa45808352f138`，保留 MIT notice。
- MADOS v1 数据或合法小型 crop，核对 Zenodo MD5 `1076b25d2797be3095d82a61105c7380`，内部另存 SHA-256 和 CC BY 4.0 attribution。
- 至少一个官方 `.pth` 权重，明确使用/再分发许可、训练编号、文件大小和 SHA-256。
- 固定 Python/PyTorch/MMCV/GDAL/CUDA 镜像、资源基线和单模型/集成策略。
- 产品与领域负责人批准污染聚合集；默认建议 `{1 Marine Debris, 6 Oil Spill}`，Sea snot 是否纳入必须明确。
- 合法真实 crop 能证明 11 波段、`rhorc` 产品、网格、CRS/transform 和期望输出。

缺任一材料时保持 `unavailable`。不得下载不明权重、用 RGB 代替 11 波段、用随机 mask 或历史结果回退。

## 2. 已确认算法身份与数据结构

| 字段 | 固定值或约束 |
| --- | --- |
| capability | `remote_sensing.pollution_segmentation` |
| repository | `https://github.com/gkakogeorgiou/mados` |
| source commit | `c20a7e972bdf111126540d8e6caa45808352f138` |
| code license | MIT |
| dataset | MADOS v1，Zenodo DOI `10.5281/zenodo.10664073`，CC BY 4.0 |
| scenes | 174 个，`Scene_0` 至 `Scene_173` |
| resolution directories | `10`、`20`、`60`，不是 `10/20/30` |
| tensor | 11 通道，统一到 10 m，crop `240 x 240` |
| classes | DN 1–15；DN 0 为未标注/忽略 |

## 3. 代码边界与建议落点

```text
backend/v2/tools/remote_sensing/adapters/
  pollution_segmentation.py
backend/v2/tests/
  test_pollution_segmentation_adapter.py
tests/fixtures/remote_sensing/pollution_segmentation/
  fixture-manifest.json
  approved-pollution-policy.json
  approved-mados-profile.json
```

handler：

```python
def run_pollution_segmentation(
    tool_input: AlgorithmToolInput,
    execution_context: ToolExecutionContext,
    execution_control: AlgorithmExecutionControl,
) -> AlgorithmToolResult:
    ...
```

使用 factory 注入 `AlgorithmArtifactManager`、`ModelRuntimeManager`、可信 model/dataset profile catalog 和
pollution policy catalog；handler 内只执行 `resolve -> validate -> workspace -> model lease -> infer -> persist -> result`。
生产依赖由 `INT-301` 注入，测试依赖固定在临时目录。禁止从 parameters、环境变量或 Google Drive 地址
直接解析权重路径。

`ALG-213` 不得修改 Registry、Router、Planner、PolicyGuard、执行器、Canonical API 或前端；集中接入由
`INT-301` 执行。不得直接调用上游 `evaluation.py` 作为生产入口，因为它依赖 split/标签、整体加载数据，
且集成投票与地理输出存在已审计缺陷。

## 4. 输入契约

建议把同一 scene/crop 的 11 波段登记成一个可信 bundle dataset：

```json
{
  "dataset_refs": [{
    "dataset_id": "ds_mados_crop_<id>",
    "role": "multispectral_scene",
    "pair_key": "Scene_134:9",
    "media_type": "application/vnd.ktp.multiband-raster-bundle"
  }],
  "parameters": {
    "pollution_policy": "ktp-pollution-v1",
    "tta": false
  },
  "output_options": {
    "artifact_roles": ["native_mask", "pollution_mask", "preview", "statistics"],
    "formats": ["image/tiff", "image/png", "application/json"]
  }
}
```

`scene_id`、`crop_id`、band 清单、实际路径和 model profile 必须由 dataset registry 解析。即使出现在 LLM
metadata 中，也不能覆盖服务端值。`AlgorithmDatasetResolver` 先验证 dataset ID、权限、bundle 文件和大小，
适配器再解析只读 bundle manifest；manifest 内路径必须经过根目录包含性检查，禁止 `..`、绝对路径和链接逃逸。

## 5. 固定 11 波段与预处理

顺序必须按下表显式声明，禁止普通字符串排序：

| channel | band | wavelength | native resolution |
| ---: | --- | ---: | ---: |
| 0 | B01 | 443 nm | 60 m |
| 1 | B02 | 492 nm | 10 m |
| 2 | B03 | 560 nm | 10 m |
| 3 | B04 | 665 nm | 10 m |
| 4 | B05 | 704 nm | 20 m |
| 5 | B06 | 740 nm | 20 m |
| 6 | B07 | 783 nm | 20 m |
| 7 | B08 | 833 nm | 10 m |
| 8 | B8A | 865 nm | 20 m |
| 9 | B11 | 1614 nm | 20 m |
| 10 | B12 | 2202 nm | 20 m |

B09/B10 不属于输入；RGB PNG、Dogliotti 和 Nechad2016 浊度文件也不进入模型张量。输入必须是 ACOLITE
Rayleigh-corrected `L2R_rhorc` 或经过单独等价性批准的 profile，不能直接接受任意 Sentinel-2 L1C/L2A DN。

首版固定处理：

1. 20 m/60 m 波段以 nearest 升采样到 10 m 参考网格。
2. 同一 crop 输出尺寸 `240 x 240`；所有通道覆盖区、CRS、transform 和目标 bbox 一致。
3. 每通道 NaN 用该通道有效均值填充；全 NaN 或无有效覆盖失败。
4. 使用以下固定 mean/std 做 z-score：

```text
mean = [0.05826760, 0.05223386, 0.04381474, 0.03570830, 0.03412902,
        0.03680401, 0.03999107, 0.03566642, 0.03965081, 0.02679930,
        0.01978944]
std  = [0.03240627, 0.03432253, 0.03548120, 0.03757690, 0.03785412,
        0.04992323, 0.05884482, 0.05545856, 0.06423746, 0.04211187,
        0.03019115]
```

任何 band、resampling、mean/std 或 `rhorc` 变化都必须提升 profile/adapter 版本并重跑等价性验证。

## 6. 类别与污染口径

| DN | class key | 默认计入污染 |
| ---: | --- | --- |
| 0 | `non_annotated` | 否；忽略/NoData |
| 1 | `marine_debris` | 是 |
| 2 | `dense_sargassum` | 否 |
| 3 | `sparse_floating_algae` | 否 |
| 4 | `natural_organic_material` | 否 |
| 5 | `ship` | 否 |
| 6 | `oil_spill` | 是 |
| 7 | `marine_water` | 否 |
| 8 | `sediment_laden_water` | 否 |
| 9 | `foam` | 否 |
| 10 | `turbid_water` | 否 |
| 11 | `shallow_water` | 否 |
| 12 | `waves_and_wakes` | 否 |
| 13 | `oil_platform` | 否 |
| 14 | `jellyfish` | 否 |
| 15 | `sea_snot` | 待批准；默认否 |

原生 15 类 mask 必须始终保留。派生污染 mask 使用版本化 policy，默认候选为 `class_id in {1,6}`；
适配器开发人员无权把 Sea snot、浑水、平台等自行纳入污染。

统计定义：

- `pollution_pixel_count`：有效预测覆盖区中 policy 命中的像元数；
- `pollution_fraction`：污染像元数 / 有效预测像元数，不以稀疏标注像元为分母；
- Marine Debris 与 Oil Spill 分项必须单独报告；
- `_conf` 是人工标注置信等级、`_rep` 是报告位置关系，均不是模型概率；
- 未校准 softmax 使用 `model_score`，不命名为概率置信度。

只有真实 CRS/transform 和有效像元面积可验证时才报告平方米/公顷。

## 7. 标准执行流程

1. `validating`：解析 bundle、模型、pollution policy；核对 11 波段、文件签名、摘要、`rhorc`、scene/crop 一致性和网格。
2. `preparing`：进入 `AlgorithmWorkspace`，以 B02/B03/B04/B08 中批准的 10 m 参考 profile 建立目标网格。
3. 按通道 nearest 重采样、NaN 处理和固定归一化；每个通道检查取消。
4. 通过 `ModelRuntimeManager.lease()` 加载一个固定权重。首版默认单模型；TTA/五模型集成必须有单独资源基线和正确性测试。
5. `running`：真实推理并校验输出形状 `[15,240,240]`、有限 logits/score 和类别值域。
6. 模型通道索引 0–14 显式映射为 MADOS DN 1–15；输出 `uint8` 中 0 只保留给 nodata/未标注。随后生成
   15 类 mask、policy 二值 mask、预览和统计。不得使用上游循环末次 `predictions` 冒充多数投票结果。
7. `persisting`：以真实 10 m 参考栅格的 CRS/transform 写 GeoTIFF，明确 nodata；用 rasterio round-trip 验证。
8. 使用 `AlgorithmArtifactManager.persist()` 持久化并计算 checksum/size。
9. `finalizing`：返回结果；`finally` 回收模型、TTA/ensemble 张量、dataset handles、工作区和可能的子进程。

上游硬编码 `+proj=latlong` 且不传 transform 的写法禁止进入适配器。

## 8. 输出规范

`predictions` 至少包含：

- `native_taxonomy`：15 类定义和每类 pixel count；
- `pollution_policy`：名称、版本、包含类 `[1,6]` 或批准值；
- `pollution`：聚合及 Marine Debris/Oil Spill 分项像元数、比例；
- `valid_prediction_pixel_count`、nodata count；
- 若通过空间验证，再包含各类面积与单位。

最低产物：

| role | runtime_kind | media_type |
| --- | --- | --- |
| `native_mask` | `segmentation_mask` | `image/tiff` |
| `pollution_mask` | `segmentation_mask` | `image/tiff` |
| `preview` | `segmentation_preview` | `image/png` |
| `statistics` | `statistics_table` | `application/json` |

GeoTIFF 的 `SpatialMetadata` 填写 CRS、bbox、10 m resolution、240×240、band/class 表。
provenance 必须记录 MariNeXt commit、权重训练编号/SHA-256、MADOS DOI/版本/crop 摘要、11 波段 profile、
mean/std/resampling、pollution policy、TTA/ensemble、参数摘要、镜像和 device，并保留 CC BY 4.0 attribution。

## 9. 错误码映射

| 条件 | 错误码 |
| --- | --- |
| bundle 未注册、crop 文件缺失 | `DATASET_NOT_FOUND` |
| 权限不足 | `DATASET_FORBIDDEN` |
| 非受支持 raster/bundle、损坏文件 | `UNSUPPORTED_FORMAT` |
| 缺/重波段、顺序错误、跨 crop、网格不一致 | `BAND_MISMATCH` |
| 非 `rhorc` profile、scene/crop/policy 参数不合法 | `INVALID_INPUT` |
| 权重缺失/摘要错误、模型环境不健康 | `MODEL_UNAVAILABLE` |
| RAM/VRAM/磁盘或输入上限超出 | `RESOURCE_EXHAUSTED` |
| deadline、取消、推理和持久化失败 | `TIMEOUT` / `CANCELLED` / `INFERENCE_FAILED` / `ARTIFACT_PERSIST_FAILED` |

错误不得输出 scene 的宿主路径、权重路径、命令、凭据或内部堆栈。

## 10. 自动化测试矩阵

- 合法固定 crop/权重得到确定的 15 类及 `{1,6}` mask、统计和 checksum。
- 逐一缺失、重复或交换 11 个波段；B8/B8A 和 B11/B12 排序不可混淆。
- 错 scene/crop、非 `rhorc`、尺寸/CRS/transform 不一致、全 NaN、部分 NaN。
- nearest 升采样与 10 m 参考网格；输出 240×240、uint8、nodata 和空间 round-trip。
- 逐类构造输出验证 1–15 图例；0 不解释为清洁水域。
- pollution policy `{1,6}`，Marine Debris/Oil Spill 分项和聚合统计守恒；Sea snot 默认不计入。
- 权重缺失/摘要错、模型输出通道不是 15、NaN logits、OOM。
- 单模型、TTA 及获批 ensemble 分支分别验证；多数投票必须实际参与最终 mask。
- 进度覆盖校验/11 波段准备/推理/持久化；取消或 deadline 后 GPU、模型引用和工作区释放。
- ArtifactStore 可下载 TIFF/PNG/JSON，media type 正确，响应/provenance 不含内部路径。
- 通过公共 contract、invoke_algorithm 和 bounded runtime 集成测试，旧工具无回退。

## 11. 真实 smoke

获得材料后，先复现官方 test split 对照：

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

该命令不能作为产品入口。适配器 smoke 必须独立读取一个受控 crop，不依赖 `_cl` 或 split 来发现输入，
不加载整个数据集，且必须修复/绕开官方投票结果未使用和伪地理参考问题。

建议未来入口：

```powershell
conda run -n <locked-env> python -m v2.tools.remote_sensing.adapters.pollution_segmentation_smoke `
  --fixture-manifest <controlled-manifest>
```

归档源码 commit、镜像、权重/MADOS crop/输出 SHA-256、11 波段检查、policy 版本、日志、耗时、峰值
RAM/VRAM、空间 round-trip、统计守恒以及失败/取消/超时清理证据。

## 12. 交付清单

- [ ] 权重许可与摘要、MADOS 数据和合法 crop、固定环境全部齐备。
- [ ] 领域/产品负责人批准污染 policy 和 Sea snot 决策。
- [ ] 11 波段、`rhorc`、nearest、mean/std 和空间 profile 已真实验证并版本化。
- [ ] 适配器不依赖标签/split 发现输入，不整体加载数据集，不复制上游错误输出路径。
- [ ] 原生 15 类、污染 mask、统计、GeoTIFF 和 provenance 一致可追溯。
- [ ] 成功、失败、OOM、取消和超时无资源泄漏。
- [ ] 自动化测试、合法 fixture、真实 smoke 和复现证据齐全。
- [ ] 不修改共享注册和 UI；交由 `INT-301/UI-401`。

全部通过后提交 `feat(ALG-213): add pollution segmentation adapter`，由独立验收人复跑。只有集中集成与
QA 通过后，能力才可从 `unavailable` 改为 `available`。

## 13. Git 交付方式

开发人员必须从最新 `origin/main` 创建独立分支：

```text
feat/ALG-213-pollution-segmentation
```

通过提交和 Pull Request 交付，禁止直接推送或合并到 `main`。最终功能提交建议为：

```text
feat(ALG-213): add pollution segmentation adapter
```

PR 标题使用 `[ALG-213] 接入污染分割适配器`。PR 必须同时包含：

- 适配器代码、自动化测试、fixture manifest、MADOS/profile/pollution policy 和环境配置；
- 分支名、最终 commit SHA、实际测试命令及结果；
- 真实 smoke、11 波段校验、GeoTIFF round-trip、统计守恒及取消/超时清理证据；
- 源码、镜像、权重、MADOS crop 和输出 SHA-256，CC BY attribution、权重许可及资源基线；
- 明确声明没有修改 Registry、Router、Planner、执行引擎、allowlist 和前端。

权重、MADOS 原始数据、容器镜像和大体积栅格禁止直接提交 Git；它们进入批准的模型库、数据存储或镜像
仓库，Git 中只提交版本、授权信息、受控引用和校验和。提交前必须确认 `git diff --check` 通过、工作树
没有无关修改，并列出 `origin/main..HEAD` 的全部提交。

开发人员最终向负责人交付：PR 链接、分支名、HEAD commit SHA、测试摘要、smoke/空间/统计证据地址和
阻断清单。独立评审及污染口径责任人签字后由集成负责人合并；适配器作者不得自行合并或执行 `INT-301` 注册。
