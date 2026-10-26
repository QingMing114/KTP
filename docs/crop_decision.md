# 农作物识别：大模型判定层（2026-10-21）

## 背景

现有农作物识别完全依赖 KDD2020 纯空间 VGG16 分类器（`backend/infra/imagery/crop_spatial.py`）：

- 权重在 NAIP RGB 地块影像上训练，推理输入是 Sentinel-2 L2A 的 B04/B03/B02 拉伸图；
- 输出是整个选区的单一类别和六类分数（玉米/棉花/大豆/春小麦/冬小麦/大麦）；
- 代码自身已声明跨传感器未经实地验证、分数不是校准置信度。

该模型缺乏区域可迁移性。本次改动保留模型分数作为**测量证据**，由配置的大模型结合**观测日期 + 地块位置**的区域物候先验给出**最终作物判定**，并完整记录判定依据。

## 判定契约

`crop` 步骤 `result` 新增 `crop_decision`，原有 `predicted_class` / `class_scores` / `model` / `warnings` 保持不变：

| 字段 | 含义 |
| --- | --- |
| `final_class_id` / `final_name_zh` | 最终判定类别（0–5） |
| `source` | `llm` / `model_fallback` / `user_confirmed` |
| `confidence` | `high` / `medium` / `low`（大模型自评） |
| `fallback_reason` / `fallback_detail` | 回退时的用户可读原因与结构化诊断（阶段、错误类型、category、上游状态码、提供方、错误信息、上游返回片段、尝试次数） |
| `llm_attempts` | 大模型尝试次数（结构校验失败会自动重试一次） |
| `rationale` | 一到三句判定依据（结构化字段，不是模型思维链） |
| `phenology` | 物候判断文本 |
| `location` | 农场预设地点标签 + AOI 质心经纬度 |
| `observed_at` | 影像观测日期 |
| `excluded_classes` | 被排除类别及原因 |
| `model_prediction` | 模型原始最高类别（不可被覆盖） |
| `fallback_reason` | 回退原因（仅 `model_fallback`） |
| `prompt_version` / `input_hash` | 提示词版本与输入指纹，用于重试一致性 |

读取统一走 `runtime/crop_decision.py::resolve_crop_class(step_result)`；历史工作流没有 `crop_decision` 时自动退回 `predicted_class`，行为与旧版本一致。

## 执行方式

| 场景 | 行为 |
| --- | --- |
| 自动执行 / 手动模式 | 判定直接生效，不额外弹卡 |
| 专业模式 | `crop` 步骤完成后暂停，生成 `phase="crop"` 确认卡：预填最终判定，六类下拉可改；确认后把用户选择写入 `yield_inputs.confirmed_crop_class_id`，`source="user_confirmed"`，然后继续后续步骤；取消则工作流取消，已完成步骤保留 |
| 大模型不可用 / 超时 / 输出非法 | `source="model_fallback"`，最终类别 = 模型最高分，后续 0.60 / 0.15 门禁与确认卡行为与改动前完全一致；`fallback_reason` 与 `fallback_detail` 记录失败原因并在卡片/报告中展示 |

### 回退诊断

2026-10-21 首次上线后出现一次回退，日志显示上游 HTTP 200、耗时约 4.7s，但结构化输出未通过本地校验：模型返回的 `excluded_classes` 每项只有 `class_id`/`name_zh`，缺少 `reason`。根因是共享 provider 的 `_build_response_contract` 只描述顶层字段类型，嵌套列表在提示词里只显示为 `array[object]`，模型无从得知每项结构。为此做了三处修正：

1. 提示词显式列出 `excluded_classes` 每项必须含 `class_id` 与 `reason`；
2. `ExcludedClass.reason` 改为可省略、`CropDecisionOutput.rationale` 允许为空（缺失时退回物候文本），不再因次要字段缺失整单回退；
3. 结构校验失败时用纠正提示词自动重试一次；仍失败才回退，并把错误类型、message、category、状态码、上游片段写入 `fallback_detail`。

已知剩余边界：更早的回退记录（如 2026-10-21 16:28 的工作流）只保存了 `fallback_reason`，没有 `fallback_detail`，界面按旧字段展示；重新执行该分析会得到新格式结果。

## 下游影响

判定结果（而非模型最高分）用于：

1. 简化估产 `resolve_simple_yield_crop`：玉米/春小麦/冬小麦可执行；判定为其他作物时返回 `crop_class_unsupported`；
2. APSIM 示例 `select_example`：玉米/大豆/小麦有模板；
3. APSIM 地块估产 `assess_yield_inputs`：`crop_source` 增加 `llm` 取值；
4. LAI 场景参数先验 `configure_workspace_lai` 的 `crop_type`。

阈值 `MIN_TOP_SCORE=0.60` / `MIN_SCORE_MARGIN=0.15` 只在 `needs_score_gate(decision)` 为真（无判定或回退）时生效，避免旧阈值否决大模型结论。

## 地点解析（2026-10-21 修复）

此前地点直接取“当前选中的农场预设名称”，用户在其他位置框选而农场仍是预设值时，判定会拿到错误地名（例如 AOI 在青海、地名却写“山东 · 邹平”）。现在改为以坐标为准：

1. 用 AOI 质心 + 内置省级行政区边界（`backend/runtime/data/china_admin_provinces.geojson`，Natural Earth 1:50m Admin-1，公有领域，简化为约 1 km，覆盖 31 个大陆省级单元）反查省份；
2. 农场预设名称只有在**质心落在该农场边界内**时才作为地点使用；
3. 质心不在农场内时置 `farm_mismatch=true`，地点改用反查到的省份，提示词明确告知“农场名称不可作为地点依据”；
4. `location` 字段包含 `province`、`source`（`farm_preset+admin_boundary` / `farm_preset` / `admin_boundary` / `coordinates_only`）、`farm_label`、`farm_mismatch`，卡片与报告展示“地点依据”，不一致时给出黄色提示。

边界：只到省级，且不含港澳台；靠近简化边界时允许约 0.05° 的缓冲、0.3° 内取最近省份；数据缺失时退化为仅经纬度并在 `source` 标明。

## 展示

- 任务详情与历史记录卡片：新增 `CropDecisionCard`，展示地点与时间、物候判断、六类模型分数、最终判定、判定依据、排除说明；
- 作物识别报告：新增“判定依据”区块，高亮最终判定，保留六类分数图与模型最高分；
- 专业模式确认卡：预填结果 + 可改选下拉框。

## 边界与诚实性

- 区域先验现阶段只依赖大模型自身知识，**未经人工整理的地区作物清单校验**；后续接入独立数据文件不改接口。
- 判定不含实地验证，报告与卡片均标注“未经实地验证、不代表识别精度”。
- 模型分数始终展示，不被判定覆盖；“模型思考过程”以结构化 `rationale` 呈现，不保存模型内部思维链。
- 大模型调用失败时按既有流程回退，不伪造判定。

## 测试

- 后端新增 `backend/tests/test_crop_decision.py`：判定保留模型证据、回退、非法输出、输入指纹、历史兼容、下游 6 类映射、专业模式确认与续跑、自动模式端到端。
- 前端新增 `src/test/cropDecisionCard.test.tsx`、`src/test/professionalReviewCrop.test.tsx`。
- 回归：后端 367 passed / 3 skipped；前端 173 passed；ESLint 与生产构建通过。
