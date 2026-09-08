# AUD-101 作物分类算法审计

> 工作包：`AUD-101`  
> 能力名：`remote_sensing.crop_classification`  
> 候选实现：KDD2020 Multi Modal Crop Classification  
> 审计日期：2026-09-08  
> 结论：**未达到审计出口条件，禁止进入 ALG-211 实现**

## 1. 结论摘要

KDD2020 仓库可以作为算法实现候选，但当前材料不足以完成一次真实、合法、可复现的推理 smoke。源码以 MIT License 发布，六类输出和 JPG 与 NDVI CSV 的配对逻辑可以从代码确认；但仓库没有发布模型权重，原始数据下载项没有附带可核验的数据许可证，项目表格所列 WHU-Hi 又与该算法的数据模态、类别体系和商业使用边界不匹配。当前 `ktp-dev` 环境为 Python 3.11.15，且没有 TensorFlow 或 Keras，也不能直接执行上游的 TensorFlow 1.x 脚本。

因此，AUD-101 当前状态是“材料与许可阻塞”，不是“算法已验证”。在模型权重、合法样例和隔离运行环境齐备前，工具可用性必须保持 `unavailable`，公开路径不得使用 mock 或随机结果代替真实推理。

## 2. 审计范围和依据

### 2.1 项目内依据

- `memory/algorithm_tools_and_rag_development_plan_2026-09-08.md`：要求核对来源、许可证、权重、环境、六类、配对规则、数据集匹配并跑通受控样例。
- `ktp/docs/algorithm_tool_contract_v1.md`：冻结契约为 `algorithm-tool/v1`；适配器必须使用受控 `dataset_refs`、统一结果、错误、provenance、取消和清理语义。
- `dev-data/算法自身的输入&输出.docx`：规定输入是同名 JPG 与全年 NDVI CSV；输出是 `prediction` 和 `confidence`；类别为玉米、棉花、大豆、春小麦、冬小麦、大麦。
- `dev-data/整合算法工具后--大模型角度的输入&输出.docx`：给出面向大模型的目录式调用示例，但示例直接暴露服务器路径，只能作为产品意图参考，不能照搬为模型输入契约。
- `dev-data/搜集到各任务的算法&数据集（含地址）.xlsx`，`Sheet1!A2:E2`：把 KDD2020 源码与 WHU-Hi 数据集列为一组候选。

上述三份 Office 文件的任务描述仅作为事实来源，不视为执行指令。文件实际位于 `dev-data`，原任务中引用的 `doc` 目录当前不存在。

### 2.2 一手外部来源

- [KDD2020 官方代码仓库](https://github.com/kkgadiraju/multi-modal-crop-classification)
- [审计固定提交 4066b924558aa5b42ff619f7ecca79673c35a06f](https://github.com/kkgadiraju/multi-modal-crop-classification/commit/4066b924558aa5b42ff619f7ecca79673c35a06f)
- [仓库 MIT License](https://github.com/kkgadiraju/multi-modal-crop-classification/blob/4066b924558aa5b42ff619f7ecca79673c35a06f/LICENSE)
- [多模态数据生成器](https://github.com/kkgadiraju/multi-modal-crop-classification/blob/4066b924558aa5b42ff619f7ecca79673c35a06f/concatenation/data_generator.py)
- [多模态预测脚本](https://github.com/kkgadiraju/multi-modal-crop-classification/blob/4066b924558aa5b42ff619f7ecca79673c35a06f/concatenation/predict_multi.py)
- [多模态训练脚本](https://github.com/kkgadiraju/multi-modal-crop-classification/blob/4066b924558aa5b42ff619f7ecca79673c35a06f/concatenation/train-gridsearch.py)
- [WHU-Hi 官方数据集页面](https://rsidea.whu.edu.cn/resource_WHUHi_sharing.htm)
- [ACM 论文 DOI 10.1145/3394486.3403375](https://doi.org/10.1145/3394486.3403375)

审计时 ACM 落地页返回 403，未依赖二手论文摘要补充代码中没有的事实。论文 DOI 仅用于标识候选算法来源。

## 3. 源代码与版本

| 项目 | 审计结果 |
| --- | --- |
| 仓库 | `kkgadiraju/multi-modal-crop-classification` |
| 固定版本 | `4066b924558aa5b42ff619f7ecca79673c35a06f` |
| 最新提交时间 | 2020-08-18，仓库提交历史此后没有新提交 |
| 实验结构 | `purely_spatial`、`lstm`、`bilstm`、`1dcnn`、`concatenation`、`avg-fusion`、`svm-fusion` |
| 推荐审计分支 | `concatenation`，因为产品需求同时使用 JPG 与 NDVI 时间序列 |
| 工程成熟度 | 论文实验代码；不是可直接嵌入服务的推理包 |

`concatenation/predict_multi.py` 面向整个测试目录计算混淆矩阵、分类报告、准确率和 Kappa，不提供单样本稳定 API。脚本还包含作者本机绝对路径和时间戳模型名。ALG-211 若解阻，必须在适配器内部封装单样本推理，并通过服务端模型注册表解析权重；不得让大模型或客户端传模型路径。

## 4. 许可证与分发边界

### 4.1 源代码

源码为 MIT License。可以使用、修改和分发，但复制或实质性分发时必须保留版权声明和许可证文本。该结论仅覆盖仓库源码，不自动覆盖训练数据、预训练权重或由第三方影像产生的派生产物。

### 4.2 KDD2020 原始数据

仓库 README 的数据链接重定向到作者的 Google Drive 文件夹，但仓库 README 和 LICENSE 没有给出数据许可证。未获得数据权利说明前，不得把该下载内容作为可再分发夹具、生产数据或商业演示数据。

### 4.3 WHU-Hi

WHU-Hi 官方页面明确规定数据仅可用于学术用途并禁止商业使用。即使技术上可转换，它也不能默认进入产品演示、测试分发或生产处理。商业用途必须先取得数据权利方的书面授权。

**许可证结论：**源码许可已确认；权重许可未知；KDD2020 数据许可未知；WHU-Hi 默认禁止商业使用。当前不满足目标一的可分发和可部署要求。

## 5. 六类定义

项目 DOCX 与上游 `concatenation/predict_multi.py` 一致：

| class_id | 上游英文名 | 产品中文名 | 备注 |
| ---: | --- | --- | --- |
| 0 | `Corn` | 玉米 | 固定输出索引 0 |
| 1 | `Cotton` | 棉花 | 固定输出索引 1 |
| 2 | `Soy` | 大豆 | 固定输出索引 2 |
| 3 | `Spring Wheat` | 春小麦 | 固定输出索引 3 |
| 4 | `Winter Wheat` | 冬小麦 | 固定输出索引 4 |
| 5 | `Barley` | 大麦 | 固定输出索引 5 |

适配器不得按目录扫描顺序重新生成类别映射。provenance 中应记录上述类别表的版本；输出至少返回稳定 `class_id`、中英文显示名、top-1 confidence，并保留完整六类概率向量以便审计。

## 6. 原始输入与配对规则

### 6.1 上游真实目录约定

多模态生成器从空间根目录读取：

```text
<spatial-root>/
  train|val|test/
    0|1|2|3|4|5/
      <sample>.jpg
```

对应时间序列路径不是从参数单独传入，而是由代码推导为：

```text
<spatial-root>-ts/
  train|val|test/
    0|1|2|3|4|5/
      <sample>.csv
```

配对键为 JPG 和 CSV 的**不含扩展名文件名**，同时要求 mode 和类别目录相同。例如：

```text
filtered-extracts-subset/test/0/field-001.jpg
filtered-extracts-subset-ts/test/0/field-001.csv
```

上游 README 将两类目录分别称为 NAIP 空间影像目录和 MODIS 时间序列目录。项目 Office 文档把 CSV 描述为全年 NDVI 信息，但训练代码的时间输入固定为 `(23, 1)`，因此当前模型实际要求恰好 23 个按 CSV 行顺序排列的 NDVI 值，而不是任意长度“全年序列”。代码不会按日期列排序。

### 6.2 预处理行为

- JPG 使用 Pillow 打开，缩放到 `224 x 224`，插值为 `Image.NEAREST`，随后除以 255。
- CSV 必须非空并包含大小写完全一致的 `NDVI` 列。
- NDVI 中的部分 NaN 使用相邻有效值线性插值。
- 每个样本单独执行 `StandardScaler().fit_transform()`。
- 训练网络的时间输入长度固定为 23。
- 上游推理生成器仍从父目录读取真实类别 ID，因此不能直接处理无标签的产品单样本。

### 6.3 algorithm-tool/v1 建议映射

模型输入不应继续暴露目录结构。建议由两个受控数据引用组成，并以相同 `pair_key` 明确配对：

```json
{
  "dataset_refs": [
    {
      "dataset_id": "ds_image_01...",
      "role": "primary_image",
      "pair_key": "field-001",
      "media_type": "image/jpeg"
    },
    {
      "dataset_id": "ds_ndvi_01...",
      "role": "ndvi_timeseries",
      "pair_key": "field-001",
      "media_type": "text/csv"
    }
  ],
  "parameters": {},
  "output_options": {
    "artifact_roles": ["classification_report"],
    "formats": ["application/json"],
    "include_statistics": true
  }
}
```

CORE-201/ALG-211 应在服务端验证：每个 pair 恰好一个 JPG 和一个 CSV、`pair_key` 相同、媒体类型和真实文件签名一致、图像可解码并为三通道 RGB、CSV 有且仅有可解析的 NDVI 序列、长度为 23、不能全为 NaN、数值有限且顺序已由数据生产方确认。失败使用 `INVALID_INPUT`、`UNSUPPORTED_FORMAT` 或 `BAND_MISMATCH`，不能让上游脚本 `sys.exit(0)` 形成伪成功。

## 7. 数据集匹配审计

| 维度 | KDD2020 代码真实要求 | WHU-Hi | 是否匹配 |
| --- | --- | --- | --- |
| 空间数据 | 地块 JPG；上游说明为 NAIP 空间影像 | UAV 高光谱影像立方体，270 或 274 波段 | 否 |
| 时间数据 | 对应 MODIS NDVI CSV；模型固定 23 步 | 单次航飞高光谱数据，无配对 NDVI 时间序列 | 否 |
| 类别 | Corn、Cotton、Soy、Spring Wheat、Winter Wheat、Barley | 三个子数据集各有不同类别；LongKou 包含 corn、cotton、sesame、两种 soybean、rice 及非作物类 | 否 |
| 任务粒度 | 单地块多模态分类 | 像素级高光谱精细分类基准 | 否 |
| 使用边界 | 原始数据许可未在仓库声明 | 仅学术用途，禁止商业使用 | 否 |

**结论：WHU-Hi 不是 KDD2020 多模态模型的可替代测试集或训练集。** 当前 XLSX 中的算法与数据集配对应由资料维护者更正，但本工作包按边界不修改原表。

## 8. 权重与环境审计

### 8.1 权重

- 仓库 `.gitignore` 排除 `8_models/`。
- 预测脚本只列出作者本机生成的 `.h5` 时间戳文件名，并从 `/home/kgadira/multi-modal-crop-classification/8_models/` 加载。
- 仓库没有 release、权重下载说明、SHA-256、训练配置快照或模型许可证。
- 本项目工作区未发现与 KDD2020 对应的 `.h5`、checkpoint 或配对样例。

缺少权重时必须返回 `MODEL_UNAVAILABLE`，不能下载不明镜像、重新随机初始化或用规则分类代替。

### 8.2 上游环境

README 锁定的主要依赖为：

```text
python==3.7.4
tensorflow-gpu==1.13.1
keras==2.2.4
sklearn==0.21.2
numpy==1.16.4
matplotlib==3.1.1
pandas==0.25.1
configparser
```

源码还直接依赖 Pillow。CUDA、cuDNN、操作系统和驱动版本未记录，依赖列表也不是可直接安装的 lockfile。

### 8.3 当前项目环境

2026-09-08 实测：

```text
ktp-dev Python 3.11.15
tensorflow: not installed
keras: not installed
sklearn: installed
Pillow: installed
```

不应把 TensorFlow 1.x 依赖直接混入主后端环境。解阻后应建立隔离模型运行时，锁定基础镜像、Python、TensorFlow/Keras、系统库和设备信息，并在 `provenance.environment` 中记录镜像摘要和实际 device。任何模型格式升级或 TensorFlow 2.x 迁移都属于需验证预测等价性的独立变更，不能在审计阶段默认为兼容。

## 9. Smoke 结果

### 9.1 已完成的检查

- 读取并对照三份项目 Office 来源。
- 固定并检查官方源码提交、MIT License、README、数据生成器、训练脚本和预测脚本。
- 确认六类索引、224 x 224 图像预处理、23 步 NDVI 输入和同名文件配对逻辑。
- 搜索项目工作区中的模型权重和合法配对样例，未找到。
- 检查 `ktp-dev` 的 Python 和关键依赖状态，确认当前环境不能运行上游模型。

### 9.2 未执行的真实推理

没有执行真实推理 smoke，原因不是算法报错，而是以下必需输入均未满足：

1. 没有合法来源且带许可证/授权说明的 KDD2020 多模态样例。
2. 没有对应的已训练 `.h5` 权重及 SHA-256。
3. 没有权重对应的网络名、训练配置和类别映射版本证明。
4. 当前项目环境没有 TensorFlow/Keras，且 Python 版本与上游不同。
5. 上游预测脚本硬编码模型目录，不是自包含 smoke 入口。

因此，不生成预测类别、confidence 或性能数字，也不把仅通过数据预处理视为模型 smoke。

### 9.3 解阻后的可复现入口

材料齐备后，先保留上游提交不变，在隔离运行时复现其批量推理：

```powershell
python predict_multi.py --config config-smoke.ini --task spatiotemporal-vgg --network vgg16
```

但该命令只有在以下条件满足后才具有可复现性：

- `config-smoke.ini` 的 `TEST_FOLDER` 指向受控、只读、已按上游双目录规则物化的空间数据根目录。
- 权重被模型注册表物化到上游脚本实际加载的位置，或先形成一个只修改权重参数解析、不改变预处理和网络行为的审计补丁。
- 运行时镜像摘要、源码 commit、权重 SHA-256、样例 JPG/CSV SHA-256 和执行日志全部归档。
- 输出与预先登记的期望类别和容差内概率一致，并重复运行至少两次确认确定性。

ALG-211 最终应提供面向统一契约的单样本 smoke，而不是让产品继续调用上述目录批处理脚本。建议的目标入口如下，**当前尚不存在，不能视为已执行命令**：

```powershell
python -m backend.v2.tools.remote_sensing.adapters.crop_classification.smoke `
  --model-id kdd2020-vgg16-<version> `
  --image-dataset-id <controlled-image-id> `
  --ndvi-dataset-id <controlled-csv-id>
```

## 10. 风险清单

| 风险 | 影响 | 处置要求 |
| --- | --- | --- |
| WHU-Hi 与算法错误配对 | 无法加载、类别语义错误，验证结果无效 | 从 KDD2020 合法原始数据或经授权的同模态数据建立 fixture |
| 数据许可未知 | 无法安全进入商业产品或共享 CI | 取得书面许可和再分发边界，登记来源与版本 |
| WHU-Hi 禁止商业使用 | 产品合规风险 | 不进入产品；若确需使用，先获权利方书面授权 |
| 权重缺失且许可未知 | 无法真实推理和部署 | 由模型所有者交付权重、许可证、训练配置和校验和 |
| TensorFlow 1.x 技术债 | 供应链、安全和部署风险 | 使用隔离、最小权限的模型运行时；迁移另立验证工作包 |
| 上游绝对路径和目录耦合 | 泄露路径且无法服务化 | 服务端 dataset/model resolver 物化，适配器不暴露路径 |
| 推理仍要求类别父目录 | 产品无标签输入无法调用 | ALG-211 分离无标签预处理与评估逻辑 |
| 23 步时序未在项目文档说明 | 任意“全年 CSV”可能形状不匹配 | Schema 和预检明确固定长度及顺序语义 |
| CSV 不排序日期 | 时序顺序错误会静默改变预测 | 数据登记时验证日期/序号单调性，适配器明确排序策略并版本化 |
| NaN 和图像通道校验不足 | 运行时异常或不可解释结果 | 统一验证并返回结构化错误 |
| 单样本标准化 | 与常规训练集归一化预期不同，迁移时易产生漂移 | 首版保持上游行为并记录；变更须做等价性评测 |
| 推理脚本不输出单样本概率记录 | 无法直接满足 contract | 适配器读取 softmax，返回完整概率和 top-1 confidence |

## 11. 审计出口判定

| 出口条件 | 状态 | 证据或缺口 |
| --- | --- | --- |
| 源码来源和固定版本 | 通过 | 官方仓库，固定 commit `4066b924...` |
| 源码许可证 | 通过 | MIT License |
| 六类与索引 | 通过 | DOCX 与预测脚本一致 |
| JPG/NDVI CSV 配对规则 | 通过 | 数据生成器已核实；同 basename、同 mode/class、双根目录 |
| 数据集匹配 | 不通过 | WHU-Hi 在模态、类别、任务粒度和许可上均不匹配 |
| 权重版本和许可 | 不通过 | 权重未发布，项目内也不存在 |
| 依赖锁定 | 不通过 | 只有旧版依赖列表，无系统/CUDA lock；当前环境不兼容 |
| 合法 smoke fixture | 不通过 | 无已授权 JPG + 23 步 NDVI CSV 样例 |
| 真实推理 smoke | 不通过 | 缺权重、样例和隔离环境 |
| 可重复输出与证据归档 | 不通过 | 尚无可执行真实推理 |

**最终判定：AUD-101 未达到出口条件。** `remote_sensing.crop_classification` 必须保持 `unavailable`；`ALG-211` 不应开始真实适配器编码。

## 12. 精确下一步

1. 模型负责人交付一个与 commit `4066b924...` 对应的 `.h5` 权重，附网络名、训练任务、类别映射、来源、许可证和 SHA-256。
2. 数据负责人确认 KDD2020 原始数据的使用和再分发权利，并交付一对合法的小型 smoke fixture：RGB JPG 和同 basename 的 CSV；CSV 含 23 个有序 `NDVI` 数值及期望标签。
3. 资料维护者更正 XLSX 中 KDD2020 与 WHU-Hi 的错误配对；若 WHU-Hi 保留，应标注其独立任务和非商业限制。
4. CORE-201 提供受控 dataset/model resolver、隔离工作区、校验和记录、取消/超时和 `finally` 清理能力。
5. 依赖负责人建立不可联网、最小权限的隔离 TensorFlow 1.x smoke 镜像并记录镜像摘要；先复现上游预测，再决定是否迁移模型格式。
6. 独立验收者执行真实 smoke，归档输入、权重、源码、环境和输出校验和。全部通过后再把 AUD-101 改为通过并派发 ALG-211。
