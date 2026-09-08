# ALG-212 地物分割接入手册

> 能力名：`remote_sensing.land_cover_segmentation`
>
> 候选算法：Dynamic Pseudo-label Assignment（DPA）
>
> 契约：`algorithm-tool/v1`
>
> 当前准入状态：**阻塞，不得开始生产适配器编码或注册为 available**

## 1. 文档用途与开工门禁

公共边界见 [`algorithm_tool_contract_v1.md`](../algorithm_tool_contract_v1.md) 和
[`algorithm_runtime_support.md`](../algorithm_runtime_support.md)，审计证据见
[`AUD-102-land-cover-segmentation.md`](../audits/AUD-102-land-cover-segmentation.md)。本文把已确认事实转为
实施步骤；标记为“待批准”的项目不得由开发人员自行设默认值。

开工前必须关闭：

- DPA 源码固定为 `49ba7eea7cda383db4559c63602fc1783601efe8`，许可证负责人完成 MIT 与
  Pytorch-UNet GPL 来源链结论。
- 取得一个明确城市/传感器的官方 checkpoint，记录许可、文件名、大小和 SHA-256。
- 取得同城市、同传感器、合法可用的四波段 TIFF 样例和标签/官方预览对照。
- 通过 GDAL/rasterio metadata 和数据负责人确认 TIFF band index 对应 Blue、Green、Red、NIR。
- 使用真实标签验证“模型通道、评估类别 ID、RGB 颜色”的版本化 crosswalk。
- 遥感与产品负责人批准 25 类到产品类映射、未映射策略和“人工地表/人工建筑”命名。
- 固定可复现运行环境、城市归一化 profile、资源上限和输出空间策略。

EuroSAT 是 10 类图块分类数据，不是 DPA 的四波段像素分割数据，不得作为 smoke 或训练替代品。

## 2. 已确认算法身份

| 字段 | 固定值或约束 |
| --- | --- |
| capability | `remote_sensing.land_cover_segmentation` |
| repository | `https://github.com/x-ytong/DPA` |
| source commit | `49ba7eea7cda383db4559c63602fc1783601efe8` |
| model | U-Net，4 输入通道，25 logits |
| source domain | Five-Billion-Pixels/GID24 |
| target domain | 城市专用 PlanetScope、GF-1 或 Sentinel-2 profile |
| window | 官方实现 `512 x 512`，stride 256 |
| output | 原始类别 GeoTIFF、产品类别 GeoTIFF、预览、统计与 provenance |

官方代码用 PIL `convert('CMYK')` 只是读取四通道的实现方式，不是遥感波段语义。产品和 provenance 中
只能使用 `blue, green, red, nir`。

## 3. 代码边界与建议落点

```text
backend/v2/tools/remote_sensing/adapters/
  land_cover_segmentation.py
backend/v2/tests/
  test_land_cover_segmentation_adapter.py
tests/fixtures/remote_sensing/land_cover_segmentation/
  fixture-manifest.json
  approved-taxonomy-mapping.json
  approved-dataset-profiles.json
```

`ALG-212` 只实现私有 handler、预处理、窗口推理、后处理和测试。不得修改 Registry、Router、Planner、
PolicyGuard、执行引擎、executor allowlist 或前端；这些由 `INT-301/UI-401` 集中处理。

```python
def run_land_cover_segmentation(
    tool_input: AlgorithmToolInput,
    execution_context: ToolExecutionContext,
    execution_control: AlgorithmExecutionControl,
) -> AlgorithmToolResult:
    ...
```

使用 factory 注入 `AlgorithmArtifactManager`、`ModelRuntimeManager`、可信 model/profile catalog 与映射
catalog；handler 内只执行 `resolve -> validate -> workspace -> model lease -> window inference -> persist -> result`。
测试使用固定临时依赖，生产依赖由 `INT-301` 注入。禁止从 parameters、文件名切片或环境变量推断
checkpoint 路径、城市和归一化 profile。

## 4. 输入契约与 profile

输入只能是一个已注册 GeoTIFF 数据引用：

```json
{
  "dataset_refs": [{
    "dataset_id": "ds_<id>",
    "role": "primary_image",
    "media_type": "image/tiff"
  }],
  "parameters": {
    "taxonomy_mapping": "ktp-land-cover-5@<approved-version>"
  },
  "output_options": {
    "artifact_roles": ["native_mask", "product_mask", "preview", "statistics"],
    "formats": ["image/tiff", "image/png", "application/json"]
  }
}
```

传感器、城市、band roles、量化/归一化、模型 ID 必须来自服务端批准的 dataset/model profile，不能相信
LLM 填入的 metadata。调用 `AlgorithmDatasetResolver.resolve()` 时要求 `primary_image`、TIFF 后缀和
`image/tiff`，并限制大小；适配器随后使用 rasterio/GDAL 校验：

- `count == 4`，band index 与批准 profile 的 `[blue, green, red, nir]` 完全一致；
- width/height、dtype、nodata、CRS、transform、resolution、bbox 可解析；
- 四个 band 同网格，无旋转/重投影歧义或已命中明确 profile；
- 数据值域、scale/offset 与 profile 匹配，16-bit 数据不得静默按 8-bit `/255` 处理；
- 城市/传感器与 checkpoint、均值/标准差及官方特殊缩放规则匹配。

无法证明 band index 时返回 `BAND_MISMATCH`，不得按文件顺序或颜色猜测。

## 5. 原始类别与 crosswalk

网络通道 0 是训练忽略类，通道 1–24 是有效预测类。官方推理调色板与 `evaluate.py` 类别顺序存在置换，
禁止直接使用 `argmax + 1`。开发必须从经真实样例确认的版本化 crosswalk 文件读取映射。

经 RGB 颜色对照得到的审计候选关系如下，但在真实标签验证前只能作为评审底稿：

| 模型通道 | 评估类别 ID | 类别 |
| ---: | ---: | --- |
| 1 | 1 | industrial area |
| 2 | 10 | paddy field |
| 3 | 11 | irrigated field |
| 4 | 12 | dry cropland |
| 5 | 13 | garden land |
| 6 | 14 | arbor forest |
| 7 | 15 | shrub forest |
| 8 | 16 | park |
| 9 | 17 | natural meadow |
| 10 | 18 | artificial meadow |
| 11 | 19 | river |
| 12 | 2 | urban residential |
| 13 | 20 | lake |
| 14 | 21 | pond |
| 15 | 22 | fish pond |
| 16 | 23 | snow |
| 17 | 24 | bare land |
| 18 | 3 | rural residential |
| 19 | 4 | stadium |
| 20 | 5 | square |
| 21 | 6 | road |
| 22 | 7 | overpass |
| 23 | 8 | railway station |
| 24 | 9 | airport |

评估 ID 0 保留给 unlabeled/NoData，不计入训练指标或产品面积。crosswalk 必须包含来源、版本、批准人、
有效日期与 SHA-256；适配器启动时校验摘要。

## 6. 产品映射规则

当前可无明显歧义映射的评估类别 ID：

- `artificial_surface`：1–9；
- `forest`：14、15；
- `grassland`：17、18；
- `water`：19–22；
- `bare_land`：24。

ID 10–13（农田/园地）、16（公园）、23（雪）及 0（未标注）尚未批准。实现不得擅自吞并到五类。
推荐保留技术类 `other_or_unmapped` 并分别输出原始 24 类、产品五类、未映射像元和面积；若业务要求
恰好五类，必须使用负责人批准的有损映射文件。

映射文件至少包含：

```json
{
  "mapping_name": "ktp-land-cover-5",
  "mapping_version": "<approved-version>",
  "source_taxonomy": "five-billion-pixels/v1",
  "unmapped_policy": "<approved-policy>",
  "mapping": {},
  "approved_by": [],
  "sha256": "<digest>"
}
```

## 7. 推理与空间产物流程

1. `validating`：解析数据、profile、checkpoint、crosswalk 和产品映射，检查所有摘要。
2. `preparing`：进入 `AlgorithmWorkspace`，打开只读 raster dataset，建立窗口计划。
3. 通过 `ModelRuntimeManager.lease()` 加载与城市/传感器绑定的模型。
4. `running`：按窗口流式读取，执行 profile 固定的量化与归一化；每个窗口前后检查取消并按已完成窗口数报告进度。
5. 按批准 crosswalk 把模型通道转换为稳定原始类别 ID，再按批准映射生成产品类别；每一步检查值域与像元守恒。
6. `persisting`：写单波段整数 GeoTIFF，不写 PIL RGB TIFF 充当分类结果。复制输入 CRS、transform、width、height、resolution、bbox，设置明确 nodata；分类重采样只用 nearest。
7. 生成独立 RGB/RGBA `segmentation_preview` 和 JSON `statistics_table`。
8. 用 rasterio 重新打开输出，验证网格、dtype、nodata、类别值域、checksum 和统计守恒后持久化。
9. `finalizing`：返回结果；所有异常、取消、超时路径释放模型、dataset handle、中间栅格和工作区。

官方成都/上海的 3/4 缩放、城市均值/标准差只能来自批准 profile，并必须进入 provenance。最终类别栅格
必须 nearest 回投到原始输入网格。

## 8. 输出规范

`predictions` 至少包含：

- `native_taxonomy`：24 个有效类、NoData、各类 pixel count；
- `product_taxonomy`：批准产品类、`other_or_unmapped`、各类 pixel count；
- `mapping_version` 与 crosswalk 版本；
- `valid_pixel_count`、`mapped_pixel_count`、`unmapped_pixel_count`。

`metrics` 中的面积只有在 CRS/transform 可验证时才允许输出；必须注明单位、像元面积方法、有效覆盖区、
NoData 和未映射策略。地理坐标系下不能简单用固定像元宽高相乘冒充平方米。

产物最低集合：

| role | runtime_kind | media_type |
| --- | --- | --- |
| `native_mask` | `segmentation_mask` | `image/tiff` |
| `product_mask` | `segmentation_mask` | `image/tiff` |
| `preview` | `segmentation_preview` | `image/png` |
| `statistics` | `statistics_table` | `application/json` |

两个 GeoTIFF 的 `SpatialMetadata` 必须填写 CRS、bbox、resolution、width、height、bands/classes。
`AlgorithmProvenance` 必须记录源码 commit、checkpoint SHA-256、城市/传感器 profile、crosswalk、产品映射、
窗口/stride、缩放、归一化、dataset version、参数摘要、镜像摘要和 device。

## 9. 错误码映射

| 条件 | 错误码 |
| --- | --- |
| 数据未注册/文件缺失 | `DATASET_NOT_FOUND` |
| 权限不足 | `DATASET_FORBIDDEN` |
| 非 TIFF、损坏或不支持的 dtype/compression | `UNSUPPORTED_FORMAT` |
| 非四波段、band role 未确认、网格不一致 | `BAND_MISMATCH` |
| 城市/传感器/profile/映射参数不匹配 | `INVALID_INPUT` |
| checkpoint 缺失、摘要错误、设备不支持 | `MODEL_UNAVAILABLE` |
| RAM/VRAM/磁盘或输入上限超出 | `RESOURCE_EXHAUSTED` |
| deadline、取消、模型失败、产物失败 | `TIMEOUT` / `CANCELLED` / `INFERENCE_FAILED` / `ARTIFACT_PERSIST_FAILED` |

错误 detail 只能包含 dataset ID、profile ID、检查名称和非敏感限额，不得包含本地路径、checkpoint 路径或栈。

## 10. 自动化测试矩阵

- 合法固定 TIFF + checkpoint 得到批准的原始类别摘要、产品映射与确定性 checksum。
- 未注册数据、权限不足、假 TIFF、损坏 TIFF、1/3/5 波段、band 顺序未知。
- CRS/transform/nodata 缺失或网格异常；16-bit profile 与 8-bit profile 不得混用。
- 城市与模型不匹配、权重缺失/摘要错误、crosswalk/映射摘要错误。
- 窗口边界、小于 512、非整除尺寸、重叠融合、成都/上海缩放与恢复。
- 模型通道置换测试：构造每个通道获胜的输出，逐项验证 24 类 crosswalk。
- 映射覆盖、未知 ID、像元数和面积守恒；未决类不被静默吞并。
- GeoTIFF round-trip：CRS、transform、width、height、dtype、nodata、类别值域完全一致。
- 进度按窗口单调；中途取消、deadline 和 OOM 后无文件、模型引用或 GPU 资源泄漏。
- ArtifactStore 下载返回正确 media type，序列化结果和 provenance 不泄露内部路径。
- 通过公共 contract/invoke_algorithm/bounded runtime 集成测试，且旧工具测试不回退。

## 11. 真实 smoke 与验收

先运行固定上游对照，再运行适配器：

```bash
python predict.py \
  --inputpath <controlled-input-directory/> \
  --outputpath <temporary-output-directory/> \
  --modelname <matching-city-checkpoint>
```

上游路径拼接、CUDA 0、城市名文件切片和 PIL 输出都只是对照限制，不得复制到产品接口。适配器 smoke
必须使用同一输入与权重，比较官方 RGB 预览，同时额外验证原始类别栅格与真实标签 crosswalk。

建议未来 smoke 入口：

```powershell
conda run -n <locked-env> python -m v2.tools.remote_sensing.adapters.land_cover_segmentation_smoke `
  --fixture-manifest <controlled-manifest>
```

归档源码、镜像、权重/输入/输出 SHA-256、profile 和映射版本、运行日志、峰值 RAM/VRAM、耗时、窗口数、
空间 round-trip 结果及取消/超时清理证据。

## 12. 交付清单

- [ ] AUD-102 所有许可、数据、权重、band、crosswalk、产品映射门禁已关闭。
- [ ] 输入只接受 dataset ID，城市/传感器/model profile 由服务端可信配置决定。
- [ ] 窗口推理不整景制造多份副本，资源上限和 `max_concurrency` 有真实基线。
- [ ] 原始类别、产品类别、未映射类和空间元数据可追溯且守恒。
- [ ] 成功、失败、取消、超时和 OOM 无资源泄漏。
- [ ] 自动化测试、合法 fixture、真实 smoke 和复现证据齐全。
- [ ] 不修改共享注册与 UI；由 `INT-301` 和 `UI-401` 后续完成。

全部通过后提交 `feat(ALG-212): add land cover segmentation adapter`，由独立验收人复跑；适配器作者无权
自行批准映射或把 ToolSpec 改为 `available`。
