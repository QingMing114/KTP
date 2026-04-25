# KTP - Knowledge-driven Task Platform

> Chat-First 遥感智能分析平台

## 项目概述

KTP（Knowledge-driven Task Platform）是一个基于大语言模型的遥感智能分析平台，采用 Chat-First 架构，用户通过自然语言对话即可完成遥感影像分析、目标检测、LAI反演等专业任务。

### 核心特性

- **Chat-First 交互**：自然语言驱动，对话即任务
- **多智能体协作**：Planner → Executor → Delegation 自动编排
- **SSE 流式响应**：实时展示 Agent 思考过程和工具调用
- **领域包系统**：可插拔的遥感分析能力（秃斑检测、PROSAIL LAI 反演等）
- **双版本架构**：V1（冻结）+ V2（活跃开发）

---

## 快速启动

### 环境要求

- Python >= 3.11
- Node.js >= 18
- Conda（推荐）

### 后端启动

```bash
cd ktp/backend
conda activate rsys
uvicorn app.main:app --host 0.0.0.0 --port 18082
```

后端默认监听 `http://0.0.0.0:18082`

### 前端启动

```bash
cd ktp/frontend
npm install
npm run dev
```

前端默认监听 `http://localhost:3000`，自动代理 `/v2`、`/chat`、`/health` 到后端。

### 访问

打开浏览器访问 `http://localhost:3000`

---

## 项目结构

```
ktp/
├── backend/                           # 后端代码
│   ├── app/main.py                    # 产品入口
│   ├── ktp_backend/                   # 后端组合根
│   │   ├── api.py                     # V2 HTTP API 定义
│   │   ├── runtime_host.py            # 运行时容器组装
│   │   └── gateway_bridge.py          # 兼容桥接（/chat, /detect, /v1/*）
│   ├── v2/                            # V2 Chat-first 运行时核心
│   │   ├── runtime/                   # 运行时引擎
│   │   │   ├── engine.py              # 核心执行引擎（Agent Loop）
│   │   │   ├── planner.py             # 规划器
│   │   │   ├── executor.py            # 执行器
│   │   │   ├── store.py               # 运行时存储接口
│   │   │   └── sqlite_store.py        # SQLite 持久化
│   │   ├── tools/                     # 工具层
│   │   │   ├── registry.py            # 工具注册表
│   │   │   └── handlers.py            # 工具处理器
│   │   ├── agents/registry.py         # Agent 注册
│   │   ├── packs/                     # 领域包
│   │   ├── policies/                  # 策略层
│   │   └── shared/schemas.py          # V2 数据模型
│   ├── apps/                          # 应用层
│   │   ├── api_gateway/               # API 网关
│   │   └── orchestrator/              # 编排器
│   ├── agents/                        # Agent 实现
│   │   ├── core_70b/                  # 核心规划 Agent
│   │   └── executor_30b/              # 执行 Agent
│   ├── services/                      # 领域服务
│   │   ├── inference_service/         # 推理服务
│   │   ├── training_service/          # 训练服务
│   │   ├── rag_service/               # RAG 服务
│   │   ├── report_service/            # 报告服务
│   │   ├── confidence_service/        # 置信度服务
│   │   └── model_registry/            # 模型注册
│   ├── infra/llm/                     # LLM 提供者
│   └── ml/baldness_rf/                # 秃斑检测随机森林
├── frontend/                          # 前端代码
│   ├── src/
│   │   ├── components/                # UI 组件
│   │   │   ├── ChatInterface.tsx      # 主聊天组件
│   │   │   ├── SessionList.tsx        # 会话列表
│   │   │   ├── MarkdownRenderer.tsx   # Markdown 渲染
│   │   │   └── Layout.tsx             # 全局布局
│   │   ├── pages/                     # 页面
│   │   │   ├── ChatPage.tsx           # 对话页
│   │   │   ├── HistoryPage.tsx        # 历史页
│   │   │   ├── SkillsPage.tsx         # 技能页
│   │   │   └── SettingsPage.tsx       # 设置页
│   │   ├── context/AppContext.tsx      # 全局状态管理
│   │   ├── services/api.ts            # API 服务层
│   │   └── types/                     # TypeScript 类型
│   ├── vite.config.ts                 # Vite 配置
│   └── package.json
├── docs/                              # 项目文档
└── var/                               # 运行时数据
    ├── runtime/                       # SQLite 数据库
    └── artifacts/                     # 产物文件
```

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ ChatPage │ │HistoryPg │ │SkillsPg  │ │Setting │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
│       └─────────────┼────────────┼────────────┘      │
│              AppContext (全局状态)                     │
│                     │ api.ts                         │
└─────────────────────┼───────────────────────────────┘
                      │ HTTP / SSE
┌─────────────────────┼───────────────────────────────┐
│              Backend (FastAPI)                        │
│                     │                                │
│  ┌──────────────────┴──────────────────────┐        │
│  │           API Gateway (路由层)            │        │
│  │  /v2/*  /chat  /detect  /v1/*  /health  │        │
│  └──────────────────┬──────────────────────┘        │
│                     │                                │
│  ┌──────────────────┴──────────────────────┐        │
│  │         V2 Runtime Engine               │        │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ │        │
│  │  │ Planner │→│ Executor │→│Delegation│ │        │
│  │  └─────────┘ └──────────┘ └──────────┘ │        │
│  │       │           │           │         │        │
│  │  ┌────┴────┐ ┌────┴────┐ ┌───┴─────┐  │        │
│  │  │  Tools  │ │ Agents  │ │  Packs  │  │        │
│  │  └─────────┘ └─────────┘ └─────────┘  │        │
│  └──────────────────┬──────────────────────┘        │
│                     │                                │
│  ┌──────────────────┴──────────────────────┐        │
│  │         SQLite Store (WAL模式)           │        │
│  │    v2_sessions  │  v2_runs  │  traces   │        │
│  └─────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### 数据模型

#### Session（会话）

```
SessionDetail
├── session_id: str          # 唯一标识
├── title: str               # 会话标题
├── created_by: str | None   # 创建者
├── latest_run_id: str | None # 最新运行ID
├── messages: list[SessionMessage]  # 内嵌消息列表
│   ├── { role: "user", content: "..." }
│   └── { role: "assistant", content: "..." }
├── created_at: str | None   # 创建时间
└── updated_at: str | None   # 更新时间
```

#### Run（运行）

```
RunDetail
├── run_id: str              # 唯一标识
├── session_id: str          # 所属会话
├── status: str              # completed | failed | abstained
├── input_message: str       # 用户输入
├── output_message: str      # 助手输出
├── assistant_message        # 富内容响应
│   └── parts[]              # 文本/工具调用/产物等
├── tool_invocations[]       # 工具调用记录
├── artifacts[]              # 产物列表
└── trace[]                  # 执行追踪
```

### 前端状态管理

使用 React Context + useReducer 模式，核心状态：

```typescript
AppState {
  sessions: Session[]           // 会话列表
  selectedSessionId: string     // 当前会话
  sessionMessages: SessionMessage[]  // 当前会话消息
  sessionRuns: Run[]            // 当前会话运行记录
  pendingRun: PendingRun        // 正在流式生成的运行
  composer: { message, attachments }  // 输入框状态
  auth: AuthState               // 认证状态
  loading: { sessions, sendMessage }  // 加载状态
}
```

---

## API 接口

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v2/sessions` | 创建会话 |
| GET | `/v2/sessions` | 列出所有会话 |
| GET | `/v2/sessions/{id}` | 获取会话详情（含消息） |
| PATCH | `/v2/sessions/{id}` | 更新会话标题 |
| DELETE | `/v2/sessions/{id}` | 删除会话及其运行 |
| GET | `/v2/sessions/{id}/state` | 获取会话状态（含最新运行） |
| GET | `/v2/sessions/{id}/runs` | 列出会话的运行记录 |

### 消息发送

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v2/sessions/{id}/messages` | 同步发送消息 |
| POST | `/v2/sessions/{id}/messages/stream` | SSE 流式发送消息 |

### 运行管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v2/runs` | 列出所有运行 |
| GET | `/v2/runs/{id}` | 获取运行详情 |
| GET | `/v2/runs/{id}/trace` | 获取运行追踪 |
| GET | `/v2/runs/{id}/state` | 获取运行状态 |
| POST | `/v2/runs/{id}/replay` | 重放运行 |

### 元数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v2/tools` | 列出工具 |
| GET | `/v2/agents` | 列出 Agent |
| GET | `/v2/domain-packs` | 列出领域包 |

### 兼容路由

| 路径 | 说明 |
|------|------|
| `/chat` | 聊天兼容入口 |
| `/detect` | 检测兼容入口 |
| `/v1/chat/completions` | OpenAI 兼容适配 |

---

## 技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | >= 3.11 | 运行时 |
| FastAPI | >= 0.115 | Web 框架 |
| Pydantic | >= 2.9 | 数据验证 |
| SQLite | WAL 模式 | 持久化存储 |
| NumPy/SciPy | - | 数值计算 |
| scikit-learn | >= 1.6 | 机器学习 |
| rasterio | >= 1.4 | 遥感影像 |
| faiss-cpu | >= 1.8 | 向量检索 |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具 |
| Tailwind CSS | 4.x | 样式框架 |
| react-markdown | 10.x | Markdown 渲染 |
| lucide-react | 1.x | 图标库 |

---

## 配置说明

### 后端环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | - | LLM 模型名称 |
| `LLM_BASE_URL` | - | LLM API 地址 |
| `LLM_API_KEY` | - | LLM API 密钥 |
| `STORE_BACKEND` | sqlite | 存储后端 |
| `RUNTIME_DATABASE_PATH` | var/runtime/ktp_v2.db | SQLite 数据库路径 |

### 前端配置

通过 `localStorage` 管理：

| Key | 说明 |
|-----|------|
| `ktp_v2_api_base_url` | API 基础地址 |
| `ktp_v2_api_key` | API Key |
| `ktp_v2_jwt_token` | JWT Token |

---

## 开发指南

### 代码规范

- 后端：Pydantic v2 模型验证，结构化日志（`logger.info("key | param=%s", value)`）
- 前端：TypeScript strict 模式，ESLint + React Hooks 规则
- 禁止使用 `any` 类型，使用具体类型替代
- 错误处理：禁止空 catch 块，至少添加注释说明

### 添加新工具

1. 在 `v2/tools/handlers.py` 中实现处理函数
2. 在 `v2/tools/registry.py` 中注册工具定义
3. 工具自动通过 `/v2/tools` 端点暴露给前端

### 添加新领域包

1. 在 `v2/packs/` 中创建包定义文件
2. 在 `v2/packs/registry.py` 中注册
3. 领域包自动通过 `/v2/domain-packs` 端点暴露

### 数据库迁移

SQLite Store 使用自动迁移机制：
- 新增列通过 `ALTER TABLE ADD COLUMN` 自动添加
- 检测 `PRAGMA table_info` 判断列是否存在
- 无需手动执行迁移脚本

---

## 运维

### 健康检查

```bash
curl http://localhost:18082/health
curl http://localhost:18082/v2/health
```

### 数据清理

通过设置页面的"系统清理"功能，或调用 API：

```bash
curl -X POST http://localhost:18082/v2/system/cleanup \
  -H "Content-Type: application/json" \
  -d '{"max_age_days": 30}'
```

### 日志

后端使用结构化日志，格式为：

```
2026-04-18 18:10:33 | INFO | module_name | event_name | key=value
```

---

## 已知限制

1. **SQLite 并发**：WAL 模式支持多读单写，高并发写入场景需考虑 PostgreSQL
2. **SSE 超时**：默认 5 分钟，长时间运行的任务可能超时
3. **消息内嵌**：消息以 JSON 数组存储在 Session 中，大量消息时性能可能下降
4. **Token 存储**：JWT 和 API Key 存储在 localStorage，生产环境建议使用 httpOnly Cookie
