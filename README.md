# KTP - Knowledge-driven Task Platform

> 面向定量遥感分析的 Chat-First 智能任务平台

KTP（Knowledge-driven Task Platform）将自然语言交互、遥感物理模型、作物生长模拟、模型推理、知识检索和可审计报告整合为统一产品。用户可以在地图或对话界面中选择区域、提交影像和任务目标；平台以异步任务与实时事件流反馈执行过程，并将结果、报告和中间产物以稳定 URL 持久化交付。

本 README 是项目的产品总览、从零配置指南和单机上线基线。代码实现是行为事实来源；详细协议与运维规则请继续参阅 [`docs/`](docs/)。

## 克隆仓库

APSIM Next Gen 以 Git submodule 方式固定在 `ApsimX/`。首次克隆请使用：

```bash
git clone --recurse-submodules https://github.com/mxlking/KTP.git
```

如果已经执行了普通的 `git clone`，再补充初始化即可：

```bash
git submodule update --init --recursive
```

子模块会检出本项目验证过的 APSIM 固定提交；需要升级时，应在 `ApsimX/` 中切换并验证目标提交，再更新主仓库记录的子模块指针。

## 目录

- [项目定位与边界](#项目定位与边界)
- [核心能力](#核心能力)
- [总体架构](#总体架构)
- [前端与后端](#前端与后端)
- [数据、任务与产物](#数据任务与产物)
- [API 与集成](#api-与集成)
- [从零开始配置](#从零开始配置)
- [部署上线](#部署上线)
- [运行、验证与运维](#运行验证与运维)
- [测试、限制与路线](#测试限制与路线)

## 项目定位与边界

KTP 的设计原则是：**数值、物理和空间结论由受控工具生成；大语言模型只负责任务理解、工具选择、编排和结果解释。** 因此，模型不会替代 PROSAIL、APSIM、影像推理或已注册模型的计算结果。

当前产品主线是一个“有界单主 Agent + 可委派子执行器”平台，而不是完全自治的通用多 Agent 系统。运行时限制最大步骤、重复工具调用、重规划次数、工具可见性及高风险操作确认，所有 Run 均保留追踪信息以支持复核和重放。

| 范围 | 当前状态 | 说明 |
| --- | --- | --- |
| 产品协议 | 已实现 | `/api/product/v1` 是前后端的长期稳定协议；新功能必须优先使用该协议。 |
| V2 运行时 | 已实现 | `/v2/*` 提供运行时和兼容读写能力，不能被无意破坏。 |
| 对话与地图工作区 | 已实现 | 会话、异步提交、SSE、地图农田、影像检索、LAI 分析和 Artifact 查看均已接入。 |
| PROSAIL LAI | 已实现 | 支持正演、LUT、像元级 TIF 反演、进度事件与自包含 HTML 报告。 |
| APSIM 作物模拟 | 已实现，需外部运行时 | 适配器可调用 APSIM Next Gen；部署环境必须提供匹配的 `Models` 可执行文件与模板目录。 |
| 推理、RAG、报告、置信度、可视化 | 已实现 | 通过本地服务适配器进入 KTP domain pack；支持 mock 与真实模型路径。 |
| 模型训练与注册 | 基础设施已具备 | 模型注册、训练服务和 Temporal 适配存在；真实训练闭环、评估和生产调度需按业务建设。 |
| 多专业 Agent 协作 | 初步启用 | 支持受限 `delegate`；专业 Agent 间的审核、权限和状态治理尚未完成。 |
| 高可用与生产监控 | 未完成 | 当前 Compose 是单机部署基线，不应作为多副本或高可用方案。 |

## 核心能力

### 用户侧功能

- 对话式任务创建、会话历史、任务模式切换、取消、重试和运行重放。
- 异步 Submission 与 SSE：页面可展示任务接收、运行、进度、产物可用、完成、失败和取消状态；断线后可查询状态恢复。
- 地图工作区：展示项目农田边界，搜索 Sentinel-2 影像，按 AOI 创建 LAI 分析任务并查看像元进度。
- 数据集管理：将本地路径注册为 Dataset，设置默认任务上下文，并在后续任务中通过 `dataset_refs` 引用。
- 分析与结果页面：浏览 Run、工具调用、追踪、置信度、报告、仪表盘及稳定 Artifact 链接。
- 知识、技能、历史、设置、批量分析和影像分析页面；登录/注册入口及前端 API 配置入口。

### 领域分析功能

| 能力 | 主要工具或服务 | 产出 |
| --- | --- | --- |
| 遥感任务编排 | `ktp.analysis_pipeline`、Planner、Executor | 可追踪的 Run、工具调用、解释和产物集合。 |
| PROSAIL 光谱与 LAI | `prosail.simulation`、`prosail.build_lut`、`prosail.invert_lai`、`prosail.invert_lai_tif` | 光谱/LUT、LAI 栅格统计、像元进度和 HTML 报告。 |
| 地图优先 LAI | canonical 农田、影像检索和 `lai-analyses` API | AOI、Sentinel 影像搜索结果、异步 LAI 任务和报告 Artifact。 |
| 作物生长模拟 | `apsim.crop_simulation` | APSIM 配置、时序输出、SQLite/CSV 解析结果和作物产量报告。 |
| 模型推理 | inference service、模型注册表、RF 秃斑识别模型 | 类别图、掩膜、模型元数据、类别语义和推理结果。 |
| 知识检索 | RAG service（FAISS、embedding、reranker） | 可追溯的本地知识片段和解释。 |
| 报告与可视化 | report/visualization service | 中文 HTML 报告、包含影像预览和工作流摘要的仪表盘。 |
| 置信度评估 | confidence service | 图像、文本、工作流融合置信度及异常掩膜告警。 |
| 训练 | training service、Temporal 适配器 | mock 训练或真实工作流启动记录；不由普通分析请求自动触发。 |

真实多类别推理必须提供 `prediction_class_semantics`（至少包含 `class_labels` 和 `target_classes`）。缺失类别语义时，系统会拒绝把多分类结果静默降级为二值掩膜。

## 总体架构

```text
浏览器（React + TypeScript + Vite）
  ├─ 对话、地图、数据集、分析结果、Debug Drawer
  └─ Canonical API Client / SSE Client
                         |
                         | HTTPS / REST / SSE
                         v
FastAPI API Gateway
  ├─ 鉴权、CORS、限流、请求体限制、统一错误处理
  ├─ Canonical Product API: /api/product/v1
  ├─ 兼容 API: /v2/*、/chat、/detect、/v1/chat/completions
  └─ 静态 Artifact / 产品 UI 服务
                         |
                         v
BackendRuntimeHost + BoundedRuntimeEngine
  ├─ Session / Submission / Dataset / Artifact SQLite Stores
  ├─ ChatFirstPlanner -> PolicyGuard -> ToolExecutor / SubExecutor
  ├─ Agent、Tool、Policy、Domain Pack 注册表
  └─ Run、Trace、Replay、MemoryManager、SSE 事件发射器
                         |
       +-----------------+------------------+-------------------+
       |                 |                  |                   |
       v                 v                  v                   v
  PROSAIL / LAI      APSIM Next Gen    KTP Python 服务      OpenAI 兼容 LLM
  物理模型与报告      作物生长模型       推理/RAG/报告/         或本地 Qwen
                                        置信度/可视化/训练
```

### 主任务链

```text
React AppContext
  -> 创建 Conversation
  -> 创建异步 Submission
  -> 订阅 Submission SSE
  -> BoundedRuntimeEngine
  -> Planner 生成受约束动作
  -> PolicyGuard 校验工具、预算和确认要求
  -> ToolExecutor 或受限 SubExecutor 执行
  -> 产出 Observation、Artifact、Trace、最终 Run
  -> SQLite 持久化并推送 SSE
  -> 前端读取稳定 Artifact URL 和 Debug 数据
```

KTP domain pack 的典型分析顺序为：模型查询 -> 推理 -> 可选知识检索 -> 报告 -> 置信度 -> 可选可视化。若真实依赖、模型或工具失败，Run 以 `failed` 结束；公共路径不会无提示地自动切换到 mock 推理。

### 代码边界

```text
ktp/
├─ backend/
│  ├─ app/、apps/api_gateway/       # FastAPI 产品入口与网关
│  ├─ api/canonical/                # 正式产品协议路由
│  ├─ runtime/、schemas/            # Submission/Dataset/Artifact Store 与对外模型
│  ├─ ktp_backend/                  # 后端组合根与兼容桥接
│  ├─ v2/runtime/                   # BoundedRuntimeEngine、Planner、Executor、Store
│  ├─ v2/tools/                     # PROSAIL、APSIM、KTP、工作区和插件工具
│  ├─ v2/{agents,policies,packs}/   # Agent、权限策略和领域包注册
│  ├─ services/                     # inference/training/rag/report/confidence/visualization
│  ├─ infra/llm/                    # heuristic、Qwen 子进程、OpenAI 兼容 LLM Provider
│  └─ ml/baldness_rf/               # 真实随机森林秃斑识别管线
├─ frontend/
│  ├─ src/pages/                    # 对话、地图、数据集、知识、分析与设置页面
│  ├─ src/context/AppContext.tsx    # Canonical 异步提交与 SSE 状态机
│  ├─ src/services/                 # 类型化 API 与 SSE 客户端
│  └─ src/components/               # Chat、地图、报告、Debug Drawer 等组件
├─ deploy/                          # Docker Compose、Nginx、部署和许可证脚本
├─ docs/                            # 架构、协议、测试、运行手册和迁移资料
├─ reports/、var/                   # 运行期报告、数据库与产物，禁止当作源代码提交
└─ tests/                           # 产品级测试；后端另有 backend/tests 与 backend/v2/tests
```

仓库内的 `ApsimX/` 是固定到特定上游提交的 Git submodule；`prosail_python/` 是 PROSAIL 实现。日常产品开发不应把 APSIM 上游源码或运行期数据误当作业务代码修改。

## 前端与后端

### 前端

- 技术栈：React 18、TypeScript、Vite 5、Tailwind CSS 4、React Router、Leaflet/Leaflet Draw、react-markdown、Vitest。
- 状态：`AppContext + useState/useMemo` 管理会话、Dataset 附件、当前 Run、异步 Submission、SSE、鉴权和 API 可用性。
- API 使用：默认调用同源 `/api/product/v1`；开发环境由 Vite 将 `/api`、`/v2`、`/chat`、`/detect`、`/health` 代理至后端。生产 Nginx 关闭 SSE 缓冲，避免长任务事件滞后。
- 产物展示：只使用后端返回的 `artifact_id`、`view_url`、`download_url` 或 `render` URL；前端不得拼接服务器本地路径。

### 后端

- 技术栈：Python 3.11、FastAPI、Pydantic v2、SQLite、SQLAlchemy、FAISS、Rasterio、NumPy/SciPy、scikit-learn、Jinja2、LangGraph、Temporal client。
- `BoundedRuntimeEngine` 执行有界 Agent Loop，记录 planner 决策、工具调用、观察结果、产物、重规划次数、委派次数和终止原因。
- 默认运行时存储可使用 SQLite（WAL）。`V2_API_STORE_BACKEND=memory` 仅适用于短生命周期开发或测试；上线必须使用持久化存储和备份卷。
- LLM 提供者可选 `heuristic`、`subprocess_qwen` 和 `openai_compatible`。生产推荐通过稳定、可鉴权、可观测的 OpenAI 兼容推理服务接入。
- 网关支持 Bearer 静态令牌或 JWT，内存限流、请求体大小限制及 CORS 配置。公开部署必须启用鉴权并限制来源域。

## 数据、任务与产物

| 资源 | 职责 | 生命周期要点 |
| --- | --- | --- |
| Dataset | 数据源注册与默认任务上下文 | v1 仅支持 `source.kind=local_path`；删除只移除注册引用，不会删除原始文件。 |
| Conversation | 用户的可归档对话容器 | 删除为软归档；后续提交可继承最新或指定 Run 的上下文。 |
| Submission | 一次异步产品请求 | 状态：`queued`、`running`、`cancelling`、`cancelled`、`completed`、`failed`。 |
| Run | 一次运行时实际执行记录 | 含助手摘要、富内容、工具调用、Artifact、Trace、终止原因和输入上下文。 |
| Artifact | 受控的结果资源 | 使用稳定 UUID 注册；通过 metadata/content/render URL 访问，避免暴露宿主机路径。 |
| Trace / Replay | 调试与审计数据 | 与稳定产品 API 分离，只能向已授权的运维或调试角色开放。 |

LAI 报告是自包含 HTML。真实像元任务开始即推送 `(0, total)`，默认每 512 个有效像元更新一次，可由 `LAI_INVERSION_BATCH` 调整。报告目录必须经 `LAI_REPORT_OUTPUT_DIR` 统一解析；Canonical Artifact 的 `render` URL 是前端正式打开报告的路径，`/v2/reports/*` 仅为兼容访问。

## API 与集成

### 正式产品协议

基路径：`/api/product/v1`。所有新前端、自动化和第三方集成均应面向此协议，而不是绑定内部 `/v2` 数据结构。

| 资源 | 主要端点 | 用途 |
| --- | --- | --- |
| Manifest | `GET /manifest` | 协商协议版本、能力、交付方式、限制与兼容适配器。 |
| 地图与 LAI | `GET /farms`、`POST /imagery/search`、`POST /lai-analyses`、`GET /lai-analyses/{id}/events` | 地图工作区、影像搜索和地图优先 LAI 异步分析。 |
| Dataset | `POST/GET /datasets`、`GET/PATCH/DELETE /datasets/{id}` | 注册及管理分析数据源。 |
| Conversation | `POST/GET /conversations`、`GET/PATCH/DELETE /conversations/{id}` | 管理对话和会话上下文。 |
| Submission | `POST /conversations/{id}/submissions`、`GET /submissions/{id}`、`GET /submissions/{id}/events`、`POST /submissions/{id}/cancel` | 异步任务创建、查询、SSE 和取消。 |
| Run / Artifact | `GET /runs/{id}`、`GET /artifacts/{id}`、`/content`、`/render` | 读取最终结果和受控产物。 |
| Debug 扩展 | `GET /debug/runs/{id}/trace|state`、`POST /debug/runs/{id}/replay` | 追踪、状态审阅和确定性 dry replay。 |

SSE 事件包括 `submission.accepted`、`submission.updated`、`run.started`、`run.progress`、`artifact.available`、`run.completed`、`run.failed`、`submission.cancelled`。客户端可使用 `Last-Event-ID` 重连；若事件缓存不可用，服务端会推送最新 Submission 快照。

创建 Dataset、Conversation、Submission 或取消任务时应携带 `Idempotency-Key: <UUID>`。同一键与不同请求体组合会返回 `409 IDEMPOTENCY_CONFLICT`。错误响应统一为：

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run run_xxx not found",
    "detail": {},
    "request_id": "req_xxx"
  }
}
```

### 兼容接口

- `/v2/*`：运行时、调试和历史产品接口。
- `/chat`、`/detect`：统一聊天和一次性检测兼容入口。
- `/v1/models`、`/v1/chat/completions`：面向 LibreChat 等 OpenAI 风格客户端的适配器。
- `/health`、`/services/health`：网关与内部服务健康检查。

兼容接口的存在不改变 Canonical API 的优先级。接口字段、分页、SSE 语义和错误码的完整约束见 [`docs/canonical_product_protocol.md`](docs/canonical_product_protocol.md)。

## 从零开始配置

### 1. 准备环境

请先安装：

| 工具 | 建议版本 | 检查命令 |
| --- | --- | --- |
| Git | 较新版本 | `git --version` |
| Python | 3.11 | `python --version` 或 `py -3.11 --version` |
| Node.js | 20 LTS | `node --version` |
| npm | 10+ | `npm --version` |

真实对话还需要一个可用的大模型服务。对新人而言，最简单的方式是使用阿里云百炼；仅检查页面和接口时也可以先使用项目内置的 `heuristic` 模式，不需要 API Key。

### 2. 申请阿里云百炼 API Key

1. 登录[阿里云百炼控制台](https://bailian.console.aliyun.com/?tab=model)。首次使用时，按页面提示开通服务；账号未完成实名认证时需要先认证。
2. 在控制台右上角确认服务地域，例如“中国（北京）”。API Key、模型和 API Host 必须属于同一地域。
3. 进入“API Key”页面，点击“创建 API Key”。个人开发可以先选择默认业务空间；团队项目建议按项目划分业务空间和权限。
4. 创建完成后，立即复制并妥善保存页面显示的完整 API Key 和 API Host。完整 Key 关闭弹窗后通常无法再次查看。
5. 模型 ID 初次可使用 `qwen-plus`。其他可用模型及地域差异以[百炼模型列表](https://help.aliyun.com/zh/model-studio/models)为准。

官方参考：[获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key) · [OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)

中国（北京）地域当前的 OpenAI 兼容地址形如：

```text
https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

请优先复制控制台实际显示的 API Host，不要照抄 `<WorkspaceId>`。不同地域的地址不同，旧账号也可能仍在使用其他官方兼容地址。

> KTP 不直接读取 `DASHSCOPE_API_KEY`。下一步需要把百炼 Key 写入项目自己的 `AGENT_LLM_OPENAI_API_KEY` 配置。

### 3. 安装依赖

#### Windows PowerShell

在项目根目录执行：

```powershell
py -3.11 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt

Copy-Item backend/.env.example backend/.env

Set-Location frontend
npm ci
Set-Location ..
```

如果系统没有 `py` 命令，但 `python --version` 显示为 3.11，可把第一行改为 `python -m venv backend/.venv`。

#### macOS / Linux

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

cp backend/.env.example backend/.env

cd frontend
npm ci
cd ..
```

如果 `rasterio`、`faiss-cpu` 等依赖安装失败，请先确认正在使用 Python 3.11 和 64 位环境。Linux 还可能需要 GDAL 等系统库；不想处理本机依赖时，可改用 Docker 环境。

### 4. 配置后端

打开 `backend/.env`，先用下面这组最小开发配置替换对应内容：

```dotenv
# 本地开发
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8005
APP_AUTH_ENABLED=false
APP_JWT_SECRET=change-me-local-development-secret-at-least-32-chars
APP_CORS_ORIGINS=http://127.0.0.1:3000

# 本地 SQLite
DATABASE_URL=sqlite:///./ktp_model_registry.sqlite3
V2_API_STORE_BACKEND=sqlite
V2_API_SQLITE_PATH=./ktp_v2_runtime.sqlite3

# 阿里云百炼
AGENT_LLM_BACKEND=openai_compatible
AGENT_LLM_OPENAI_API_BASE=https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
AGENT_LLM_OPENAI_API_KEY=sk-替换为你申请的百炼Key
AGENT_LLM_OPENAI_MODEL_NAME=qwen-plus
AGENT_LLM_OPENAI_DISABLE_THINKING=false
AGENT_LLM_REQUEST_TIMEOUT_SECONDS=180
```

配置时请注意：

- `AGENT_LLM_OPENAI_API_BASE` 使用百炼控制台显示的实际 API Host，并保留末尾的 `/compatible-mode/v1`。
- Base URL 中不要再追加 `/chat/completions`，KTP 会自动追加该路径。
- `AGENT_LLM_OPENAI_API_KEY` 填完整 Key，不要保留示例值 `EMPTY`。
- `AGENT_LLM_OPENAI_MODEL_NAME` 填模型 ID，例如 `qwen-plus`，不要填写模型展示名称。
- `.env` 已被 Git 忽略。不要把 API Key 写入 README、源代码、截图或提交记录。

如果暂时没有百炼 Key，只想确认项目能否启动，可改为：

```dotenv
AGENT_LLM_BACKEND=heuristic
```

`heuristic` 只提供确定性的兜底逻辑，不能代表真实大模型效果。

### 5. 启动项目

打开两个终端，均从项目根目录开始。

#### Windows PowerShell

终端 1——启动后端：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port 8005 --reload
```

终端 2——启动前端：

```powershell
Set-Location frontend
npm run dev
```

#### macOS / Linux

终端 1——启动后端：

```bash
cd backend
.venv/bin/python -m uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port 8005 --reload
```

终端 2——启动前端：

```bash
cd frontend
npm run dev
```

浏览器通常会自动打开 <http://127.0.0.1:3000>。如果没有自动打开，请手动访问该地址。

### 6. 验证是否成功

先检查后端：

```bash
curl http://127.0.0.1:8005/health
```

能收到 JSON 响应说明后端已经监听。随后打开前端并发送一条简单消息，例如：

```text
你好，请介绍一下你能完成哪些遥感分析任务。
```

如果使用百炼配置，后端日志中不应出现 `401`、`invalid_api_key` 或上游 `404`。如果使用 `heuristic`，页面可以工作，但回复能力会明显受限。

### 7. 常见问题

#### 百炼返回 401 或 `invalid_api_key`

- 检查 Key 是否复制完整，前后是否带有多余空格或引号。
- 检查 Key 与 API Host 是否来自同一地域、同一业务空间。
- 确认 Key 有权访问 `AGENT_LLM_OPENAI_MODEL_NAME` 指定的模型。
- 如果 Key 曾经出现在提交记录或聊天截图中，请立即去百炼控制台重置或删除它。

#### 大模型接口返回 404

最常见原因是 Base URL 配错。正确配置写到 `/compatible-mode/v1` 即可：

```dotenv
AGENT_LLM_OPENAI_API_BASE=https://<你的API-Host>/compatible-mode/v1
```

不要把 `/chat/completions` 写进环境变量；也不要把 DashScope 原生接口的 `/api/v1` 与 OpenAI 兼容接口混用。

#### 前端提示后端不可用

1. 访问 <http://127.0.0.1:8005/health>，确认后端已启动。
2. 确认后端使用 `8005` 端口，且没有被其他程序占用。
3. 如果后端改用了其他端口，创建 `frontend/.env.local`：

   ```dotenv
   VITE_API_PROXY_TARGET=http://127.0.0.1:你的后端端口
   ```

4. 修改后重启 `npm run dev`。

#### Python 提示找不到模块

确保从 `backend/` 目录运行 Uvicorn，并使用刚创建的虚拟环境 Python。不要混用系统 Python 和 `.venv` 中的 Python。

#### SQLite 提示无法打开数据库

快速开始使用的是相对于 `backend/` 的数据库路径。请确认该目录可写，并从 `backend/` 目录启动后端。生产环境应改为明确的持久化路径或外部数据库，并做好备份。

#### 首次安装很慢

后端包含 Rasterio、FAISS、SciPy 等科学计算依赖，前端也需要下载 npm 依赖。首次安装耗时较长是正常现象。网络受限时请使用团队统一的可信镜像源，不要随意下载来历不明的二进制包。

### 8. 可选：配置 APSIM

在运行后端的主机或容器中准备 APSIM 发布物，并在 `backend/.env` 中设置：

```dotenv
APSIM_ROOT=/opt/apsim
APSIM_MODELS_BIN=/opt/apsim/bin/Release/net8.0/linux-x64/publish/Models
```

`APSIM_MODELS_BIN` 必须存在且可执行，`APSIM_ROOT` 中需要包含任务使用的模板和依赖。未配置时，普通对话和其他工具仍可使用；调用 `apsim.crop_simulation` 时会明确失败，不会伪造模拟结果。

## 部署上线

### 部署模型

[`deploy/docker-compose.yml`](deploy/docker-compose.yml) 提供“前端 Nginx + 后端 FastAPI + 命名数据卷”的单机部署基线：前端容器对外暴露 `FRONTEND_PORT`，后端容器可通过 `BACKEND_PORT` 供内网运维访问，前端同网段代理 API 与 SSE。

这不是高可用编排。若需要多副本、滚动发布、共享 Artifact 存储、集中日志、外部数据库、GPU 调度或跨节点任务队列，应在 Kubernetes/Swarm 或企业平台上补齐相应架构，并先完成压测和故障演练。

### 1. 生产配置文件

在受控服务器上：

```bash
cd ktp/deploy
cp .env .env.backup
${EDITOR:-vi} .env
```

仓库中的 `deploy/.env` 仅是配置样例，不能直接用于上线。创建或编辑实际 `.env` 时至少设置以下项目，并把文件权限限制为部署账号可读：

```dotenv
FRONTEND_PORT=8080
BACKEND_PORT=8005

APP_NAME=ktp-product
APP_ENV=production
LOG_LEVEL=INFO
APP_AUTH_ENABLED=true
APP_AUTH_TOKEN=<at-least-32-random-bytes>
APP_JWT_SECRET=<at-least-32-random-bytes>
APP_CORS_ORIGINS=https://app.example.com
APP_RATE_LIMIT=300
APP_RATE_WINDOW=60
APP_MAX_REQUEST_BODY_MB=50

AGENT_LLM_BACKEND=openai_compatible
AGENT_LLM_OPENAI_API_BASE=https://llm.example.com/v1
AGENT_LLM_OPENAI_API_KEY=<secret>
AGENT_LLM_OPENAI_MODEL_NAME=<approved-model-name>
AGENT_LLM_REQUEST_TIMEOUT_SECONDS=180

KTP_LICENSE_SKIP=0
```

注意：当前 Compose 文件已显式传递其列出的环境变量。若需要使用自定义 `KTP_LICENSE_SECRET`、`APP_CORS_ORIGINS`、APSIM 路径、报告目录、外部数据库或其他后端变量，必须在 `deploy/docker-compose.yml` 的 `backend.environment` 中显式透传，并为路径增加安全的只读/读写挂载。仅写入 `.env` 不会自动注入一个未列出的容器环境变量。

### 2. 许可证门禁

仓库提供 `backend/scripts/license_guard.py`，可生成和验证绑定机器指纹、有效期和功能集的 `license.key`。当前网关启动路径**尚未调用** `check_license_on_startup()`；Compose 虽挂载了 `license.key`，但该文件本身不会阻止未授权实例启动。因此，现状不能宣称许可证已构成生产访问控制。

正式上线前必须在受测的应用启动路径接入该校验，并使失败状态阻止服务就绪；然后在最终持久化卷和运行容器中完成如下验证：

```bash
cd ktp/deploy
docker compose exec backend python scripts/license_guard.py machine-id
docker compose exec backend python scripts/license_guard.py validate
```

发证端和运行端必须使用同一受控的 `KTP_LICENSE_SECRET`，并将生成的 `license.key` 放置到 `ktp/deploy/license.key`。不要依赖源码中的默认密钥，也不要在生产环境使用 `KTP_LICENSE_SKIP=1`。变更许可证、密钥或持久化卷后，必须再次验证。

### 3. 构建与启动

```bash
cd ktp/deploy
docker compose config                 # 先审查变量展开结果
docker compose build --no-cache
docker compose up -d
docker compose ps
docker compose logs --tail=200 backend
```

也可使用 `./deploy.sh build`、`./deploy.sh start` 或 `./deploy.sh deploy`。脚本适用于 Bash/Linux；上线前仍应人工审查 `.env`、许可证和镜像标签。默认 Compose 端口为前端 `3002`、后端 `8005`，可由环境变量覆盖。

### 4. TLS、反向代理与网络

Compose 中的 Nginx 仅负责静态站点、API/SSE 反向代理和基础安全响应头，**不终止 TLS**。正式公网部署应在其前配置受控的 Ingress、Nginx、Caddy 或云负载均衡器，完成：

- 仅开放 `443/tcp`；后端 `8005` 应限制为内网/运维网段访问。
- 配置域名证书、HTTP 到 HTTPS 跳转、HSTS 和 TLS 1.2+。
- 保留 SSE 必需的禁缓冲、至少 600 秒读取超时和正确的 `X-Forwarded-*` 头。
- 将 `APP_CORS_ORIGINS` 设为实际前端域名，而非空值或 `*`。
- 使用 Secret Manager、部署平台 secret 或受限权限文件保存 API key、JWT secret、令牌和许可证密钥；不得提交到 Git。

### 5. 生产化缺口清单

在将该单机基线用于对外服务前，负责人必须确认以下事项已经闭环：

- 已为 Canonical API 的创建、SSE、取消、Artifact URL 和 Dataset 幂等性补充自动化回归测试。
- 已定义 Submission 内存事件队列的 TTL 清理与跨重启幂等语义。
- 已为运行时数据库、Artifact/报告、RAG 索引、模型和输入数据建立备份、恢复与保留策略。
- 已验证真实 LLM、APSIM、模型、STAC、影像读取、磁盘配额和网络超时，而非只验证 mock 路径。
- 已限制 Debug/Replay、模型管理和本地路径 Dataset 注册的访问权限，并按数据分级审查日志与产物。
- 已将许可证校验接入实际启动路径，并已在最终容器、持久化卷和失效许可证场景下验证启动被拒绝。
- 已完成压测、容量估算、告警、漏洞扫描、依赖锁定和回滚演练。

## 运行、验证与运维

### 启动后验收

```bash
curl -fsS http://127.0.0.1:8005/health
curl -fsS http://127.0.0.1:8005/services/health
curl -fsS http://127.0.0.1:8005/api/product/v1/manifest \
  -H 'Authorization: Bearer <APP_AUTH_TOKEN>'
```

建议将以下端到端路径纳入发布验收：

1. 打开前端，登录或配置 Bearer Token，确认 Manifest、会话列表与地图加载成功。
2. 上传/注册一份受控测试 GeoTIFF，创建 Conversation，提交一条 LAI 或遥感分析请求。
3. 验证 `submission.accepted -> run.started -> run.progress -> artifact.available -> run.completed` SSE 序列；断开网络后验证状态查询与重连。
4. 打开 Canonical Artifact `render` URL，确认 HTML 报告以 `200 text/html` 返回且不依赖宿主机路径。
5. 在已配置真实 APSIM/模型的环境执行一条真实任务，并记录模型版本、输入版本和预期结果范围。
6. 使用授权最小化的账号检查 Debug/Replay、取消、限流和未授权访问返回正确错误码。

### 备份与恢复

单机 Docker 基线将后端数据保存在名为 `<compose-project>_backend_data` 的命名卷中。上线前须将其替换或扩展为可备份存储，并同时备份额外挂载的报告、模型、RAG 和输入数据。示例：

```bash
# 维护窗口内执行；先确认卷名
docker volume ls
docker run --rm \
  -v <compose-project>_backend_data:/data:ro \
  -v "$PWD/backups":/backup \
  alpine tar czf /backup/ktp-backend-$(date +%F).tgz -C /data .
```

恢复演练必须在隔离环境验证：停止服务 -> 恢复卷/挂载目录 -> 启动 -> 校验许可证 -> 查询旧 Conversation、Run 与 Artifact。数据库备份不等于模型和文件产物备份。

### 日志、升级与回滚

```bash
cd ktp/deploy
docker compose logs -f --tail=200 backend
docker compose logs -f --tail=200 frontend
```

升级应使用不可变镜像标签而非仅使用 `latest`：备份 -> 记录当前镜像摘要与配置 -> 预发验证 -> 逐项健康检查和 E2E 验收 -> 切流。出现协议、SSE、数据库或报告回归时，应回滚到已验证镜像和对应的兼容配置；不要在未备份的持久化卷上执行破坏性清理。

## 测试、限制与路线

### 常用验证命令

```bash
cd ktp/backend
.venv/bin/python -m pytest -q tests v2/tests

cd ../frontend
npm run lint
npm run build
npm run test
```

可执行 `backend/scripts/demo_baldness_real_flow.py` 进行真实 RF 秃斑识别演示。该脚本是开发/验收辅助工具，不是生产部署编排。

### 已知限制

- SQLite WAL 适合单机轻中度并发，写入仍受单写者约束；多副本部署需要外部共享数据库和重新验证的 Store 语义。
- Submission SSE 使用内存事件队列，队列清理和跨重启幂等性仍是后续可靠性工作项。
- Canonical API 的自动化测试覆盖度低于 V2 运行时；发布应优先补足异步、取消、SSE、Artifact 和 Dataset 回归。
- LLM 输出具有不确定性。工具权限、物理约束、输入校验和人工复核不可省略，尤其不能将演示或 mock 结果用于生产决策。
- APSIM、真实模型、STAC、影像数据和 GPU/LLM 服务均为外部运行依赖；Docker 基线不会替你打包、授权或运维这些系统。
- 前端当前将 JWT/API 配置保存在浏览器存储；面向公网的正式身份体系应升级为受控会话、httpOnly Cookie、令牌轮换和审计策略。

当前开发顺序以 `G:/Code/ktp_product/memory/algorithm_tools_and_rag_development_plan_2026-09-08.md` 为准：先完成算法工具统一契约和三个真实遥感算法的工具化闭环，再启动真实 RAG。阶段 0 的共享基线与 APSIM/障碍物检测决策见 [BASE-001 共享开发基线](docs/base_001_baseline.md)。

## 参考文档

- [Canonical Product Protocol](docs/canonical_product_protocol.md)
- [Architecture](docs/architecture.md)
- [V2 Architecture](docs/v2_architecture.md)
- [System Manual](docs/system_manual.md)
- [MVP Runbook](docs/mvp_runbook.md)
- [Testing](docs/testing.md)
- [PROSAIL Integration](docs/prosail_integration.md)
- [Agent Runtime Acceptance](docs/agent_runtime_acceptance.md)
- [项目记忆索引（仅限维护者）](../memory/MEMORY.md)
