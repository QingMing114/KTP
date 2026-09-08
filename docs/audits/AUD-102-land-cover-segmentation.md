# AUD-102 地物分割算法审计

> 工作包：`AUD-102`  
> 能力名：`remote_sensing.land_cover_segmentation`  
> 候选实现：Dynamic Pseudo-label Assignment（DPA）  
> 契约：`algorithm-tool/v1`  
> 审计日期：2026-09-08  
> 审计结论：**有条件不通过。不得进入 `ALG-212` 实现，直至权重、输入波段、空间输出和 25 类到产品类别映射的出口条件全部关闭。**

## 1. 范围与证据层级

本审计只评估 DPA 是否具备接入冻结契约的条件，不修改算法、运行时、Office 原始资料或共享代码。事实采用以下优先级：

1. DPA 官方仓库、论文和 Five-Billion-Pixels 官方项目页。
2. 项目冻结契约 `docs/algorithm_tool_contract_v1.md`。
3. 项目提供的三份需求材料。材料只代表当前需求或搜集记录，不被视为外部算法事实。

内部材料实际位于 `G:/Code/ktp_product/dev-data`：

- `算法自身的输入&输出.docx`
- `整合算法工具后--大模型角度的输入&输出.docx`
- `搜集到各任务的算法&数据集（含地址）.xlsx`，相关记录为 `Sheet1!A3:E3`

DOCX 通过 bundled Python 与 `python-docx` 只读提取；XLSX 通过 bundled Python 与 `openpyxl` 只读检查。未编辑或导出 Office 文件。文档渲染因本机 bundled 环境未提供 `soffice.exe` 而未完成，但正文和表格内容可完整提取。本审计不依赖视觉版式判断。

外部一手来源：

- [DPA 官方仓库](https://github.com/x-ytong/DPA)，审计固定到 `49ba7eea7cda383db4559c63602fc1783601efe8`。
- [DPA README](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/README.md)。
- [DPA 推理脚本](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/predict.py)。
- [DPA 训练脚本](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/train.py)。
- [DPA GID24 数据加载器](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/dataloaders/datasets/gid24.py)。
- [DPA 目标域数据加载器](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/dataloaders/datasets/target.py)。
- [DPA 标签颜色定义](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/evaluate.py)。
- [Five-Billion-Pixels 官方项目页](https://x-ytong.github.io/project/Five-Billion-Pixels.html)。
- [论文 HTML：Enabling Country-Scale Land Cover Mapping with Meter-Resolution Satellite Imagery](https://arxiv.org/html/2209.00727v2)。
- [DPA MIT 许可证](https://raw.githubusercontent.com/x-ytong/DPA/49ba7eea7cda383db4559c63602fc1783601efe8/LICENSE)。
- [EuroSAT 官方仓库](https://github.com/phelber/EuroSAT)。

## 2. 执行摘要

| 审计项 | 结论 | 阻断级别 |
| --- | --- | --- |
| 算法身份 | Excel 中的项目页能够追溯到官方 DPA 仓库；DPA 是 Dynamic Pseudo-label Assignment，不是名称相同的其他 DPA。 | 通过 |
| 源代码许可 | DPA 仓库声明 MIT；但 README 说明部分代码改编自 GPL-3.0 的 Pytorch-UNet，派生关系及分发义务需要许可证负责人复核。 | 阻断发布 |
| 数据许可 | Five-Billion-Pixels 页面只称“open source license”，当前公开页面未显示可归档的具体许可证正文；不得据此批准再分发。 | 阻断数据分发 |
| 权重 | 官方提供五个中国城市对应模型的下载入口，但未给出版本、文件清单、许可证、大小或 SHA-256；本地也没有 DPA 权重。 | 阻断实现与 smoke |
| 数据集匹配 | Excel 填写的 EuroSAT 与 DPA 不匹配。DPA 使用 Five-Billion-Pixels/GID24 作为源域，并使用城市目标影像。 | 阻断 |
| 四波段 | 论文的语义是 Blue、Green、Red、NIR；代码却通过 PIL `convert('CMYK')` 读取。当前不能把 “CMYK” 当作遥感波段顺序。 | 阻断 |
| 25 类 | 模型为 25 个 logits：通道 0 被忽略，通道 1–24 是有效类别。`dataloaders/utils.py` 的模型通道调色板顺序与 `evaluate.py` 的类别表顺序不同，不能简单用通道号作为类别 ID。 | 阻断 |
| 产品 5 类 | 只有 18 个官方有效类别可无明显歧义地进入五个产品组；农田、园地、公园、雪和未标注区不能由适配器作者擅自归类。 | 阻断 |
| 空间产物 | 官方脚本使用 PIL 读写，输出 RGB TIFF，不保留 CRS、仿射变换、NoData 或像元值类别栅格。 | 阻断 |
| 可运行性 | 官方脚本固定 CUDA/GPU 0、城市归一化和城市权重；没有依赖锁或 CPU 路径。 | 阻断 |
| 最小 smoke | 因权重、匹配样例和可核验的数据许可缺失，本次没有伪造 smoke 成功。已给出复现步骤。 | 未执行 |

**裁决：** `AUD-102` 的调查工作完成，但 `ALG-212` 入口仍关闭。最先需要解决的是“选定服务场景和城市模型”“取得并校验权重与合法样例”“确认四波段的真实 TIFF band index”“批准产品映射”。

## 3. 算法与代码审计

### 3.1 身份与版本

官方项目页把代码链接明确指向 `x-ytong/DPA`。官方 README 将 DPA 展开为 Dynamic Pseudo-label Assignment，并描述为基于 U-Net 的无监督域适应方法：从有标签源域迁移到无标签目标域，用于大尺度地表覆盖制图。

建议锁定：

```text
repository: https://github.com/x-ytong/DPA
commit: 49ba7eea7cda383db4559c63602fc1783601efe8
algorithm_name: Dynamic Pseudo-label Assignment
algorithm_version: git:49ba7eea7cda383db4559c63602fc1783601efe8
backbone: U-Net, 4 input channels, 25 output logits
```

不得只记录 `main` 或 `DPA`，因为名称存在歧义且分支可变化。

### 3.2 许可结论

DPA 仓库根许可证是 MIT。仅从仓库声明看，复制、修改和分发需要保留版权与许可文本。

但官方 README 同时写明部分代码改编自 [milesial/Pytorch-UNet](https://github.com/milesial/Pytorch-UNet)，该上游仓库的 [LICENSE](https://raw.githubusercontent.com/milesial/Pytorch-UNet/master/LICENSE) 是 GPL-3.0。这里存在需要正式处理的许可证来源链问题：DPA 根目录的 MIT 声明与被承认的 GPL 上游改编是否兼容，不能由工程审计直接裁定。

进入发布前必须由许可证负责人完成：

1. 对 `unet/` 等改编文件做来源比对，确认哪些文件构成派生代码。
2. 确认部署形态是否属于分发，以及相应源代码、声明和许可证义务。
3. 形成书面结论；不接受“仓库根目录写 MIT”作为唯一依据。

Five-Billion-Pixels 官方页称数据集“released under the open source license”，但页面未列出许可证名称或许可正文。本审计不能确认其商业使用、再分发、裁剪夹具分发和模型训练衍生物条款。数据进入代码仓或演示包前必须获得并归档实际许可文本。

### 3.3 依赖与环境

官方 README 只给出：

```text
pip install tensorboardX tqdm
```

这不是可复现环境。源码还直接依赖：

- Python
- PyTorch 与 CUDA
- torchvision
- NumPy
- Pillow
- tensorboardX
- tqdm

仓库没有 `requirements.txt`、Conda 环境文件、容器文件、Python 版本、PyTorch/CUDA 版本或包哈希。训练脚本使用 CUDA AMP、NCCL 和分布式接口；推理脚本无条件加载到 CUDA 0，并调用 `model.cuda()` 和 `patch.cuda()`，因此官方实现没有 CPU smoke 路径。

接入实现还必须增加 GDAL/rasterio 一类的地理栅格依赖，用于读取 band metadata、窗口推理和保留 CRS/transform/NoData。该依赖属于 KTP 适配层，不应伪称为官方 DPA 依赖。

建议 `ALG-212` 在真实 smoke 后生成独立、固定的推理镜像，并记录 Python、torch、torchvision、CUDA、Pillow、NumPy、rasterio/GDAL 的精确版本和镜像摘要。在 smoke 前不猜测版本号。

## 4. 数据、波段与空间要求

### 4.1 正确数据源

论文和官方项目页说明：

- 源域是 Five-Billion-Pixels，它扩展自 GID；官方代码模块仍命名为 `gid24.py`。
- 数据包含 150 景 GF-2 影像，4 m 空间分辨率，超过 50 亿已标注像元。
- 目标域使用无标签 PlanetScope、GF-1 和 Sentinel-2 影像，分别覆盖指定城市。
- 官方发布的预测权重是五个中国城市模型，输入影像所在城市必须与模型对应。

因此，内部文档中的“如 GID24 数据集”可解释为代码层旧命名，但正式 provenance 应写 `Five-Billion-Pixels`，并记录下载版本/校验和。

### 4.2 EuroSAT 不匹配

`Sheet1!A3:E3` 把 DPA 对应数据集写为 EuroSAT。这一组合不可用于 DPA 适配：

| 项目 | Five-Billion-Pixels / DPA | EuroSAT |
| --- | --- | --- |
| 任务 | 像素级语义分割与无监督域适应 | 图块级地表覆盖分类 |
| 传感器 | 源域 GF-2；目标域 PS/GF-1/Sentinel-2 | Sentinel-2 |
| 输入 | 大幅四波段影像/裁剪 | 64×64 图块；RGB 或 13 波段版本 |
| 标签 | 24 个有效像素类加未标注类 | 10 个图块类别 |
| 输出粒度 | 每像元标签 | 每图块类别 |

EuroSAT 官方仓库说明其有 27,000 个地理参考图块、13 个 Sentinel-2 波段和 10 类。它既不能提供 DPA 的 25-logit 标签，也不能替代城市目标域。`ALG-212` 必须从依赖和样例清单中移除 EuroSAT，除非未来另建独立分类能力并重新审计。

### 4.3 四波段语义

论文给出的 GF-2 四个光谱范围按以下顺序描述：

1. Blue：0.45–0.52 μm
2. Green：0.52–0.59 μm
3. Red：0.63–0.69 μm
4. NIR：0.77–0.89 μm

论文对 GF-1、PlanetScope 和 Sentinel-2 目标数据也使用 Blue、Green、Red、NIR 四个对应波段。官方网络定义为四输入通道。

然而，官方数据加载和推理代码都调用 `Image.open(...).convert('CMYK')`。内部 DOCX 也因此写成“四通道 CMYK 模式”。这只能证明官方 Python 管线依赖 PIL 返回四个通道，不能证明 TIFF band index 的语义是印刷色 C/M/Y/K，也不能证明所有目标传感器以同一 band index 存储 B/G/R/NIR。

冻结以下接入规则：

- 产品层对外只允许语义波段 `blue, green, red, nir`，不得暴露或记录为 `CMYK`。
- 数据引用必须携带传感器、产品级别、四个 band role 和空间元数据，或命中经过审计的固定数据 profile。
- 适配器必须用 GDAL/rasterio 检查 `count == 4`、width/height、dtype、nodata、CRS、transform、每个 band description/role 和一致分辨率。
- 无法确定 band index 时返回 `BAND_MISMATCH`；不能按文件出现顺序猜测。
- 在取得官方样例后，用 GDAL metadata、官方说明和可视化三方交叉确认 `[B,G,R,NIR]` 的实际 index，再固化 profile。
- 16-bit 源数据必须按官方项目页建议通过 GDAL 读取；PIL 的 8-bit 归一化仅能复现已处理影像路径，不能静默截断 16-bit 数据。

### 4.4 空间要求

不同目标模型对应不同传感器和分辨率：PlanetScope 约 3 m、GF-1 8 m、Sentinel-2 10 m；源域 GF-2 是 4 m。空间分辨率不是一个固定常量，必须进入 provenance 与输入验证。

官方 `predict.py`：

- 将整景影像读入内存；
- 使用 512×512 patch、256 像元 stride 和重叠裁剪；
- 对成都和上海影像先缩放到原尺寸的 3/4，推理后最近邻放回原尺寸；
- 根据模型名选择城市专用均值/标准差；
- 通过 PIL 保存 RGB TIFF。

因此官方输出只是一张彩色预览，不是可用于 KTP 地图与统计的地理参考分类栅格。`ALG-212` 必须同时生成：

1. 单波段整数 GeoTIFF，像元值使用批准的稳定类别 ID，并通过经样例验证的模型通道交叉表转换；使用最近邻、原 CRS、原 transform、原尺寸和明确 NoData。
2. 产品映射后的单波段 GeoTIFF；未决/不适用类必须使用独立值，不能丢失或算入五类面积。
3. RGB/RGBA 预览，可作为 `segmentation_preview`，但不能代替分类栅格。
4. JSON 统计和 provenance，面积计算必须注明投影、像元面积方法、NoData 与未映射类。

如果模型为了复现需要临时重采样，最终类别结果必须最近邻回投到输入网格，并记录中间尺度和目标网格检查。输入 CRS 缺失时不得输出带虚假 CRS 的地图产物；应失败或降级为明确的非地理预览，具体策略由产品契约评审决定。

## 5. 原生 25 类

论文列出 24 个有效类别，并把杂项或难以判定区域作为 unlabeled。模型使用 25 个 logits，训练损失忽略数值 0。

官方仓库存在两种顺序：`evaluate.py` 用下面的“评估类别 ID”把 RGB 标签编码为 0–24；`dataloaders/utils.py` 则按另一顺序把模型通道 1–24 的预测转换成颜色。下表通过共同的 RGB 颜色建立交叉关系。该交叉关系能解释官方预览，但仍需使用一份真实单通道训练标签验证其数值编码。

| 评估类别 ID | 模型通道 | 官方类别 | 中文工作名 | 颜色 RGB |
| ---: | ---: | --- | --- | --- |
| 0 | 0（训练忽略；官方推理不输出） | unlabeled | 未标注/忽略 | 0,0,0 |
| 1 | 1 | industrial area | 工业区 | 200,0,0 |
| 2 | 12 | urban residential | 城镇住宅 | 250,0,150 |
| 3 | 18 | rural residential | 农村住宅 | 200,150,150 |
| 4 | 19 | stadium | 体育场 | 250,200,150 |
| 5 | 20 | square | 广场 | 150,150,0 |
| 6 | 21 | road | 道路 | 250,150,150 |
| 7 | 22 | overpass | 立交桥 | 250,150,0 |
| 8 | 23 | railway station | 火车站 | 250,200,250 |
| 9 | 24 | airport | 机场 | 200,150,0 |
| 10 | 2 | paddy field | 水田 | 0,200,0 |
| 11 | 3 | irrigated field | 水浇地 | 150,250,0 |
| 12 | 4 | dry cropland | 旱地 | 150,200,150 |
| 13 | 5 | garden land | 园地 | 200,0,200 |
| 14 | 6 | arbor forest | 乔木林 | 150,0,250 |
| 15 | 7 | shrub forest | 灌木林 | 150,150,250 |
| 16 | 8 | park | 公园 | 200,150,200 |
| 17 | 9 | natural meadow | 天然草地 | 250,200,0 |
| 18 | 10 | artificial meadow | 人工草地 | 200,200,0 |
| 19 | 11 | river | 河流 | 0,0,200 |
| 20 | 13 | lake | 湖泊 | 0,150,200 |
| 21 | 14 | pond | 池塘 | 0,200,250 |
| 22 | 15 | fish pond | 鱼塘 | 150,200,250 |
| 23 | 16 | snow | 雪 | 250,250,250 |
| 24 | 17 | bare land | 裸地 | 200,200,200 |

官方 `predict.py` 对 `output[:, 1:, :, :]` 求最大值，得到 0–23 的临时索引，再按 `dataloaders/utils.py` 的 24 色表生成 RGB 预览。这不但隐藏了“网络通道 1–24”和“预览索引 0–23”的偏移，还隐藏了模型通道顺序与 `evaluate.py` 评估类别顺序的置换。适配器必须使用经真实标签验证的显式 crosswalk；禁止直接 `argmax + 1`。0 仅用于 NoData、未标注或批准的拒判策略。

## 6. 25 类到产品 5 类

内部大模型需求文字要求识别“林地、草地、水体、人工建筑、裸地等生态要素”。这只定义了展示目标，没有定义穷尽、互斥的映射，也没有说明农田、公园和雪如何处理。

### 6.1 可作为评审底稿的保守映射

以下仅是基于官方类别名称和上节“评估类别 ID”的候选映射，不是已批准配置：

| 产品候选类 | 可直接归入的原始 ID | 说明 |
| --- | --- | --- |
| artificial_surface（人工地表） | 1–9 | 比“人工建筑”更准确，因为包含广场、道路、立交、车站和机场。产品若坚持“人工建筑”，必须决定是否排除非建筑人工面。 |
| forest（林地） | 14, 15 | 乔木林、灌木林。 |
| grassland（草地） | 17, 18 | 天然草地、人工草地。 |
| water（水体） | 19–22 | 河流、湖泊、池塘、鱼塘。 |
| bare_land（裸地） | 24 | 裸地。 |

### 6.2 不得自动吞并的类别

| 原始 ID | 未决原因 | 必须由谁决定 |
| ---: | --- | --- |
| 0 | 未标注/忽略，不应计入任何五类。 | 算法负责人定义拒判与 NoData；产品负责人确认展示。 |
| 10–12 | 农田不等同于草地或裸地；丢弃会使面积总和不守恒。 | 遥感领域负责人 + 产品负责人。 |
| 13 | garden land 在论文分类体系中属于农业相关地类，不能仅凭中文“园地”归为林地。 | 遥感领域负责人。 |
| 16 | park 是人工非农业植被区域，可能包含林、草和人工面，单标签无法无损映射。 | 遥感领域负责人 + 产品负责人。 |
| 23 | 雪不是裸地；当前五类没有容纳项。 | 产品负责人。 |

建议产品输出保留 `other_or_unmapped` 第六个技术值，即使 UI 只突出五类。统计必须同时报告原始 24 类、产品五类和未映射比例，保证面积守恒。若业务强制输出恰好五个值，必须由产品负责人签署有损映射表及其统计影响。

### 6.3 映射配置要求

映射必须是版本化数据，不得硬编码在模型后处理分支中。至少记录：

```text
source_taxonomy: five-billion-pixels/v1
mapping_name: ktp-land-cover-5
mapping_version: 待批准
mapping_owner: 待指定
effective_date: 待批准
unmapped_policy: 待批准
```

`AlgorithmToolResult.validation.checks` 必须包含映射版本、原始 ID 覆盖率、未知 ID 数量、像元总数守恒和面积总数守恒。

## 7. 权重与模型适配性

官方 README 提供 `model_DPA` Google Drive 目录，并明确“输入影像所在城市需要与模型对应”。已知命名示例为 `unet_wuhan.pth.tar`，训练代码保存的是 checkpoint 字典中的 `state_dict`。

当前缺失：

- 五个权重的完整文件名、大小、SHA-256 和许可证。
- 每个权重对应的训练数据版本、训练参数、PyTorch/CUDA 版本和指标。
- 权重下载内容是否仍可匿名取得的可复现记录。
- 产品示例 `GF2_PMS2__L1A0001886305-MSS2.tif` 对应城市和模型。该文件不在官方 README 列出的目标域文件中。

在这些信息齐备前，ToolSpec 必须为 `availability = unavailable`，原因至少写明“缺少已审计的城市权重和匹配输入 profile”。不能使用随机权重、空 mask 或图像阈值作为回退。

## 8. 最小 smoke 方案与本次结果

### 8.1 本次未执行真实 smoke

工作区没有 DPA 源码副本、DPA checkpoint 或匹配的 Five-Billion-Pixels/城市目标 TIFF。官方权重目录没有可在本审计环境中归档的文件清单和校验和；数据许可也未关闭。GitHub 仓库通过官方网页和 raw 文件完成审计，但命令行 clone 受到当前网络代理限制。

因此本次不声称推理跑通。使用合成 TIFF 或随机 checkpoint 只能测试脚本形状，不能满足开发计划所要求的真实算法 smoke。

### 8.2 可复现 smoke 步骤

在出口条件关闭后，由 `AUD-102`/`ALG-212` 执行者在隔离环境完成：

1. 检出 DPA commit `49ba7eea7cda383db4559c63602fc1783601efe8`。
2. 从官方 `model_DPA` 取得一个城市 checkpoint；记录来源 URL、文件名、大小和 SHA-256。
3. 从官方目标数据取得同一城市的一景四波段 TIFF，或由数据负责人提供已获授权的等价样例；记录数据摘要和许可。
4. 用 `gdalinfo -json` 记录 count、dtype、band description、color interpretation、CRS、transform、extent、resolution、NoData 和尺寸。
5. 人工确认四个 band index 到 Blue/Green/Red/NIR 的映射以及城市归一化 profile。
6. 建立经过锁定的 CUDA 环境，先运行官方命令作为对照：

   ```bash
   python predict.py \
     --inputpath <matching-city-input-directory-with-trailing-separator> \
     --outputpath <temporary-output-directory-with-trailing-separator> \
     --modelname <city-checkpoint-path>
   ```

7. 官方脚本通过后，用 KTP 候选适配层对同一输入运行，比较 RGB 预览像素与原始类栅格。
8. 用官方 RGB 预览和真实标签验证“模型通道 -> 评估类别 ID”的交叉表；再验证适配输出 CRS、transform、width、height 与输入相同，类别值只属于 0–24，产品映射守恒，临时文件和 GPU 句柄在成功、失败与取消路径均清理。
9. 记录峰值主存、峰值显存、耗时、patch 数、checkpoint SHA-256、输入 SHA-256 和输出 SHA-256。

### 8.3 官方脚本复现陷阱

- `inputpath + name` 和 `outputpath + name` 使用字符串拼接，路径需要尾部分隔符。
- 通过 `args.modelname[5:-8]` 猜城市名，完整路径可能破坏切片；正式适配器必须显式传 `model_profile`，不能解析文件名。
- 固定加载到 CUDA 0，不支持 CPU，也不尊重 KTP 设备调度。
- `os.listdir` 未排序，批量输出顺序不稳定。
- 成都和上海使用强制 3/4 缩放，必须进入 provenance。
- 输出为 RGB TIFF，不含原始类别值和地理元数据。

## 9. 资源与运行风险

| 风险 | 证据与影响 | `ALG-212` 要求 |
| --- | --- | --- |
| 整景内存 | 官方脚本一次把整景转为 tensor，并分配全尺寸 float64 `classMap`。6800×7200 的 `classMap` 单项约 373 MiB，尚未包含四通道图像、padding 和 RGB 副本。 | 使用 raster window/分块流式读取；禁止全景多副本；设主存预算。 |
| 显存 | 512×512 U-Net patch、25 logits；官方未给显存基线且固定 GPU 0。 | `max_concurrency=1` 起步；真实 smoke 后填写最小显存；捕获 OOM 为 `RESOURCE_EXHAUSTED`。 |
| 长时任务 | 4 m 大景约需数百个重叠 patch；官方没有进度、取消、deadline。 | 每个窗口检查取消并报告 `running` 进度；超时返回 `TIMEOUT`。 |
| 输出膨胀 | 原始 ID GeoTIFF、产品 GeoTIFF、预览和统计会产生多份数据。 | 临时窗口写入、压缩、BigTIFF 判断、产物大小上限和持久化失败清理。 |
| 城市/传感器漂移 | 权重和归一化是城市专用；任意四波段 TIFF 可能产生貌似合理但错误的结果。 | dataset profile 与 model profile 强绑定；不匹配返回 `INVALID_INPUT` 或 `MODEL_UNAVAILABLE`。 |
| 16-bit 截断 | 官方页面明确区分 16-bit GDAL 读取和已处理 8-bit PIL 读取。 | 禁止把 16-bit 数据直接走 `ToTensor()/255`；为每个 profile 固化量化/归一化。 |
| 地理信息丢失 | PIL 输出不保存 KTP 要求的空间元数据。 | rasterio/GDAL 写 GeoTIFF并做网格一致性测试。 |
| 类别重编号与置换 | 官方预览将通道 1–24 变成索引 0–23；推理调色板与评估类别表还存在顺序置换。 | 用真实标签验证版本化 crosswalk；内部使用稳定 0–24 类别 ID；预览颜色显式映射。 |
| 许可 | 代码上游许可链、数据许可和权重许可未关闭。 | 许可证负责人书面批准后才可打包或发布。 |

## 10. 与 `algorithm-tool/v1` 的接口建议

### 10.1 输入

建议使用一个受控 GeoTIFF 数据引用，不允许模型或用户传宿主路径：

```json
{
  "dataset_refs": [
    {
      "dataset_id": "ds_<id>",
      "role": "primary_image",
      "media_type": "image/tiff",
      "metadata": {
        "sensor": "待审计 profile",
        "band_roles": ["blue", "green", "red", "nir"],
        "model_profile": "待审计城市模型"
      }
    }
  ],
  "parameters": {
    "taxonomy_mapping": "ktp-land-cover-5@<approved-version>"
  },
  "output_options": {
    "artifact_roles": ["native_mask", "product_mask", "preview", "statistics", "provenance"],
    "formats": ["image/tiff", "image/png", "application/json"],
    "include_visualization": true,
    "include_statistics": true
  }
}
```

`sensor`、`band_roles` 和 `model_profile` 只能由服务端 dataset registry 校验或补充，不能相信 LLM 自报。

### 10.2 输出

成功结果至少包含：

- `predictions.native_taxonomy`：0–24 类定义和像元统计。
- `predictions.product_taxonomy`：批准后的五类及未映射统计。
- `metrics.pixel_count`、`mapped_pixel_count`、`unmapped_pixel_count`、各类面积和面积单位。
- `artifacts`：原始类别 GeoTIFF、产品 GeoTIFF、预览、统计和 provenance。
- `provenance`：DPA commit、checkpoint 文件标识与 SHA-256、城市/传感器 profile、数据摘要、参数摘要、映射版本、环境镜像摘要。
- `validation`：band、CRS、网格、类别范围、映射守恒、NoData 和产物校验。

空间产物必须填充 `SpatialMetadata.crs/bbox/resolution/width/height/bands/classes`。访问地址由 KTP ArtifactStore 生成，不返回本地路径。

### 10.3 错误语义

- 不是 TIFF、压缩/数据类型不支持：`UNSUPPORTED_FORMAT`
- 不是四波段或 band role 不明：`BAND_MISMATCH`
- 城市/传感器与模型 profile 不匹配：`INVALID_INPUT`
- checkpoint 缺失、摘要不符或设备不支持：`MODEL_UNAVAILABLE`
- 主存/显存不足：`RESOURCE_EXHAUSTED`
- 推理异常：`INFERENCE_FAILED`
- 取消、超时和持久化失败：使用冻结契约对应错误码

错误 detail 不得包含真实文件路径、原始命令、内部堆栈或下载凭据。

## 11. `ALG-212` 入口条件

以下条件必须全部满足，`AUD-102` 才能从“有条件不通过”转为“通过”：

- [ ] 许可证负责人完成 DPA/Pytorch-UNet 来源链审查，并给出允许的部署与分发方式。
- [ ] 归档 Five-Billion-Pixels/目标城市数据的明确许可文本，确认小型测试夹具是否可分发。
- [ ] 从官方来源取得至少一个城市 checkpoint，记录文件名、大小、SHA-256 和使用许可。
- [ ] 取得与 checkpoint 同城市、同传感器的合法四波段 TIFF smoke 样例。
- [ ] 通过 GDAL metadata 和官方证据确认 TIFF band index 为 Blue、Green、Red、NIR；固化 dataset profile。
- [ ] 明确产品要支持的城市/传感器。未知域输入不得默认执行。
- [ ] 取得一份真实单通道源标签和对应官方 RGB 标签/说明，验证“标签数值、模型通道、评估类别 ID、RGB 颜色”四者的交叉表。
- [ ] 遥感领域负责人和产品负责人批准 25 类到产品类的版本化映射，尤其是评估类别 ID 10–13、16、23 和 0。
- [ ] 决定 UI 名称使用“人工地表”还是更窄的“人工建筑”，并与映射内容一致。
- [ ] 在锁定环境真实跑通一景 smoke，记录输入、模型、输出摘要和资源基线。
- [ ] 证明候选 GeoTIFF 输出保留 CRS、transform、尺寸、NoData，类别与面积统计守恒。
- [ ] 给出 CUDA/CPU 可用策略、最小显存/主存、超时、取消点和 `max_concurrency`。
- [ ] 将 ToolSpec 保持 `unavailable`，直到上述材料进入模型/数据注册表并通过复核。

## 12. 建议责任分工

| 事项 | 责任角色 | 产出 |
| --- | --- | --- |
| 代码与上游许可链 | 许可证/合规负责人 | 书面使用、部署和分发结论 |
| 数据与权重许可、摘要 | 数据治理负责人 | 许可归档、下载记录、SHA-256 |
| 城市/传感器/波段 profile | 遥感算法负责人 | 经样例验证的 profile 与归一化参数 |
| 25 到产品类映射 | 遥感领域负责人 + 产品负责人 | 版本化、签署的映射表和未映射策略 |
| 空间产物与面积口径 | GIS 负责人 | CRS、重投影、NoData、面积计算规范 |
| 资源基线 | `ALG-212` 实现者，独立验收人复核 | smoke 记录、主存/显存/耗时/取消证据 |

适配器实现者不得单独批准类别映射、输入域或许可结论。
