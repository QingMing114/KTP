# KTP 产品技术文档

## 项目概述

KTP（Knowledge-driven Task Platform）是一个 Chat-First 的智能分析平台，用户通过对话触发遥感分析工作流（斑秃识别、LAI 反演、作物长势分析等）。采用前后端分离架构，后端基于 FastAPI + Agent Loop，前端基于 React + TypeScript + Vite。

---

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React)                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Layout   │  │ ChatInt  │  │ MarkdownRenderer  │  │
│  │ (Sidebar)│  │ (Main)   │  │ (Streaming/Hist)  │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ AppCtx   │  │ API Svc  │  │ ErrorBoundary     │  │
│  │ (State)  │  │ (HTTP)   │  │ (Global)          │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
└─────────────────────┬───────────────────────────────┘
                      │ SSE / REST (Vite Proxy)
┌─────────────────────▼───────────────────────────────┐
│                   Backend (FastAPI)                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Security │  │ API      │  │ QueryEngine       │  │
│  │ (Auth/   │  │ (Routes) │  │ (Agent Loop)      │  │
│  │  Rate/   │  │          │  │  ├─ Planner       │  │
│  │  Trace)  │  │          │  │  ├─ Executor      │  │
│  └──────────┘  │          │  │  └─ Delegation    │  │
│                │          │  └───────────────────┘  │
│  ┌──────────┐  │          │  ┌───────────────────┐  │
│  │ Runtime  │  │          │  │ LLM Provider      │  │
│  │ Store    │  │          │  │ (OpenAI/Qwen)     │  │
│  │ (Mem/SQL)│  │          │  └───────────────────┘  │
│  └──────────┘  └──────────┘  ┌───────────────────┐  │
│                              │ Tool Handlers      │  │
│                              │ (PROSAIL/KTP/WS)   │  │
│                              └───────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 前端架构

### 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.2 | UI 框架 |
| TypeScript | 5.2 | 类型安全 |
| Vite | 5.4 | 构建工具 |
| Tailwind CSS | 4.x | 样式（本地安装，非 CDN） |
| react-markdown | 10.x | Markdown 渲染 |
| react-syntax-highlighter | 16.x | 代码高亮 |
| lucide-react | 1.8 | 图标库 |

### 目录结构

```
src/
├── App.tsx                    # 路由入口 + ErrorBoundary
├── main.tsx                   # 应用挂载 + index.css 导入
├── index.css                  # Tailwind v4 入口
├── components/
│   ├── ChatInterface.tsx      # 主聊天组件（流式渲染/工具详情/快捷键）
│   ├── MarkdownRenderer.tsx   # Markdown 渲染（代码高亮/复制）
│   ├── Layout.tsx             # 全局布局（可折叠侧边栏）
│   ├── SessionList.tsx        # 会话列表（时间/删除确认）
│   └── ErrorBoundary.tsx      # 全局错误边界
├── context/
│   └── AppContext.tsx          # 全局状态管理（SSE/流式/重试）
├── pages/
│   ├── ChatPage.tsx           # 对话页
│   ├── AnalysisPage.tsx       # 分析工具页
│   └── ResultsPage.tsx        # 分析结果页
├── services/
│   └── api.ts                 # API 服务层（超时/SSE 解析/类型）
├── hooks/
│   └── useArtifactClick.ts    # 产物点击处理
├── types/
│   ├── index.ts               # 核心类型定义
│   └── api.ts                 # API 类型定义
└── utils/
    └── index.ts               # 工具函数
```

### 核心功能

#### 1. 流式 Markdown 渲染

- **StreamingMarkdown**：流式输出时自动检测 Markdown 语法，实时渲染
- **MarkdownRenderer**：历史消息使用完整渲染（代码高亮/表格/GFM）
- 双模式切换：流式用 `StreamingMarkdown`，历史用 `MarkdownRenderer`

#### 2. 思考过程展示

- `ThinkingProcess` 组件：可折叠，显示规划/委派/工具调用步骤
- 默认折叠，点击展开
- 流式时显示脉冲动画指示当前步骤

#### 3. 工具调用可视化

- `ToolCallBlock`：可折叠的工具调用卡片（输入参数）
- `ToolResultBlock`：可折叠的工具结果卡片（输出摘要）
- 类似 Claude Code 的 tool use 可视化

#### 4. 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+N | 新建对话 |
| Ctrl+K | 聚焦输入框 |
| Esc | 停止生成 |
| Ctrl+Shift+P | 快捷键面板 |
| Enter | 发送消息 |
| Shift+Enter | 换行 |

#### 5. 其他功能

- 滚动到底部按钮（距离 >120px 时出现）
- 对话导出为 Markdown
- 消息时间戳
- 会话删除二次确认
- 会话列表相对时间
- 消息重试/重新生成
- 侧边栏折叠保留图标导航
- 文件上传（📎 按钮）
- 停止生成（AbortController）
- 产物链接安全校验（href 协议白名单）

---

## 后端架构

### 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.100+ | Web 框架 |
| Pydantic | 2.x | 数据模型 |
| uvicorn | 0.23+ | ASGI 服务器 |
| httpx | 0.24+ | HTTP 客户端（LLM 调用） |

### API 端点

#### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /v2/health | V2 健康检查 |
| GET | /v2/system/manifest | 系统清单 |

#### 会话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /v2/sessions | 创建会话 |
| GET | /v2/sessions?offset=0&limit=50 | 列出会话（分页） |
| GET | /v2/sessions/{id} | 获取会话详情 |
| PATCH | /v2/sessions/{id} | 更新会话（标题） |
| DELETE | /v2/sessions/{id} | 删除会话 |
| GET | /v2/sessions/{id}/state | 获取会话状态 |
| GET | /v2/sessions/{id}/runs | 列出会话的运行 |
| POST | /v2/sessions/{id}/messages | 同步发送消息 |
| POST | /v2/sessions/{id}/messages/submit | 异步提交消息 |
| POST | /v2/sessions/{id}/messages/stream | SSE 流式发送 |

#### 运行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /v2/runs?offset=0&limit=50 | 列出运行（分页） |
| GET | /v2/runs/{id} | 获取运行详情 |
| GET | /v2/runs/{id}/trace | 获取运行追踪 |
| GET | /v2/runs/{id}/state | 获取运行状态 |
| POST | /v2/runs/{id}/replay | 重放运行 |

#### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /v2/upload | 文件上传（类型/大小限制） |
| GET | /v2/tools | 列出工具 |
| GET | /v2/agents | 列出 Agent |
| GET | /v2/domain-packs | 列出领域包 |
| GET | /v2/datasets | 列出数据集 |
| POST | /v2/datasets/register | 注册数据集 |

### 数据模型（关键新增）

#### TokenUsageV2

```python
class TokenUsageV2(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model_name: str | None = None
```

#### 分页

```python
class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False
```

#### 错误响应

```python
class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: str | None = None
    request_id: str | None = None
```

#### 模型偏好

```python
class RequestContextV2(BaseModel):
    # ...existing fields...
    model_preference: Literal["fast", "powerful", "default"] | None = None
```

### 安全中间件

| 中间件 | 功能 |
|--------|------|
| APIKeyMiddleware | Bearer Token / X-API-Key 认证（hmac.compare_digest 防时序攻击） |
| RateLimitMiddleware | 令牌桶限流（支持 X-Forwarded-For 反向代理） |
| RequestTraceMiddleware | 请求追踪（X-Request-Id） |

### SSE 流式架构

```
Client ←── SSE ─── FastAPI (async) ── Queue ── Thread (sync) ── QueryEngine
                │                                     │
                │  heartbeat (15s)                    │  event_sink callback
                │  is_disconnected() 检测             │  RunEventV2 events
                └─────────────────────────────────────┘
```

- 心跳间隔：15 秒
- 超时：300 秒
- 客户端断连自动检测并通知 worker 终止

---

## 运行指南

### 启动后端

```bash
cd /home/D/liumeng/ktp_product
/home/D/liumeng/miniconda3/envs/rsys/bin/python -m uvicorn v2.apps.api.main:app --host 0.0.0.0 --port 18190
```

### 启动前端

```bash
cd /home/D/liumeng/ktp_product/v2/apps/web
npm run dev -- --host 0.0.0.0 --port 3001
```

### 环境要求

- Python 3.10+（推荐 rsys conda 环境）
- Node.js 18+
- 依赖：`Pillow`, `scikit-image`, `sqlalchemy`, `python-multipart`

---

## 与 Claude Code 的差距与路线图

### 已实现 ✅

| 能力 | 实现状态 |
|------|---------|
| 流式 Markdown 渲染 | ✅ StreamingMarkdown 组件 |
| 思考过程展示 | ✅ ThinkingProcess 可折叠 |
| 工具调用可视化 | ✅ ToolCallBlock/ToolResultBlock |
| 键盘快捷键 | ✅ Ctrl+N/K/Esc/Ctrl+Shift+P |
| 停止生成 | ✅ AbortController |
| 代码高亮+复制 | ✅ react-syntax-highlighter |
| 对话导出 | ✅ Markdown 格式 |
| Token 使用量 Schema | ✅ TokenUsageV2 |
| 模型偏好选择 | ✅ model_preference 字段 |
| API 分页 | ✅ PaginatedResponse |
| 会话 CRUD | ✅ PATCH/DELETE |
| 文件上传安全 | ✅ 类型/大小/路径遍历防护 |
| SSE 断连感知 | ✅ is_disconnected() |
| 时序攻击防护 | ✅ hmac.compare_digest |
| 反向代理 IP | ✅ X-Forwarded-For |
| 全局错误边界 | ✅ ErrorBoundary |
| Token 用量实时追踪 | ✅ provider.py 提取 usage + context_manager 累积 |
| 成本估算 | ✅ COST_PER_MILLION_TOKENS 定价表 |
| 上下文窗口动态管理 | ✅ build_context_window() 基于 token 预算 |
| Token 用量前端显示 | ✅ TokenUsageBadge 组件 |
| SSE 事件携带 token_usage | ✅ RunEventV2.token_usage |
| 优雅关机 | ✅ lifespan 上下文管理器 |
| SSE 超时控制 | ✅ 300s 总超时 |
| Health Check 依赖检查 | ✅ store/LLM 可用性 → ok/degraded |
| 异步 send_message | ✅ asyncio.to_thread() |
| 级联删除 | ✅ delete_session 同时删除关联 runs |
| 速率限制内存泄漏修复 | ✅ TTL 过期清理 + 最大条目限制 |
| 中文 token 估算优化 | ✅ CJK 1.8 chars/token vs EN 3.5 |
| CORS 安全警告 | ✅ 通配符时输出 warning |
| 文件上传权限 | ✅ os.chmod(0o600) |
| PROSAIL 路径配置化 | ✅ 环境变量 PROSAIL_PATH |

### 进行中 🔄

（无 — 以下项目已全部完成）

### 计划中 📋

| 能力 | 优先级 | 说明 |
|------|--------|------|
| 对话分支 | P1 | 从历史消息分叉新对话 |
| 多用户认证（JWT） | P1 | 替代单一 API Key |
| 异步原生引擎 | P2 | 消除 Thread+Queue 桥接 |
| 工具确认流程 | P2 | 危险操作需用户确认 |
| SQLite 性能优化 | P2 | 索引/连接池/事务 |
| 配置外部化 | P2 | 硬编码移入 settings |
| Structured Output API | P3 | 替代手动 JSON 提取 |
| 可观测性（Prometheus） | P3 | 指标/结构化日志 |
