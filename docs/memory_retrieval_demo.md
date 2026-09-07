# Markdown 规范检索演示

本演示让 KTP Agent 在每次规划前，从指定的 Markdown 目录检索与用户问题相关的规范片段，并将结果作为 `retrieved_memory` 传给 planner。它是只读的：不会由对话自动修改规范文档。

## 1. 准备规范目录

目录必须包含一个 `MEMORY.md` 索引，索引使用普通 Markdown 链接列出可检索文档：

```markdown
# 规范索引

- [Canonical Product Protocol](canonical_api_spec.md)
```

现有仓库根目录的 `memory/` 已符合这个格式，其中包含 `canonical_api_spec.md`。运行期只读取它；不要启用自动写回。

桥梁养护手册演示使用 `memory/bridge/专用养护手册框架/`。该目录的 `MEMORY.md` 已索引 `专用养护手册框架.md`，可作为独立知识库使用。

## 2. 配置

在启动后端的环境中设置：

```dotenv
V2_API_MEMORY_DIR=G:/Code/ktp_product/memory
V2_API_MEMORY_TOP_K=5
V2_API_MEMORY_MAX_CHARS=2000
V2_API_MEMORY_AUTO_WRITE_ENABLED=false
```

`V2_API_MEMORY_DIR` 应改为实际规范目录的绝对路径。配置未设置时，记忆功能保持关闭。

桥梁养护手册的实际配置为：

```dotenv
V2_API_MEMORY_DIR=G:/Code/ktp_product/memory/bridge/专用养护手册框架
```

## 2.1 启动本地演示

在 PowerShell 中使用下面的命令。必须先切换到 `backend`，否则 Python 无法把
`apps` 识别为顶级后端包，也不会读取 `backend/.env`：

```powershell
$backendDir = (Resolve-Path '.\backend').Path
Set-Location $backendDir
$env:PYTHONPATH = $backendDir

# Keep the uvicorn invocation on one line: PowerShell backticks fail when
# followed by a space and can silently omit --app-dir.
python -m uvicorn --app-dir $backendDir apps.api_gateway.main:app --host 127.0.0.1 --port 8005 --reload
```

另开一个 PowerShell 启动前端：

```powershell
Set-Location .\frontend
npm run dev
```

访问 `http://localhost:3000/chat`。Vite 默认将 API 请求代理到
`http://127.0.0.1:8005`。

## 3. 演示问题

启动 KTP 后，在普通 chat 中提问：

- `创建数据集使用哪个 canonical 接口？`
- `提交任务后如何订阅进度事件？`
- `哪些接口支持 Idempotency-Key？`
- `artifact 的 URL 在前端应该如何使用？`

Agent 应从 `canonical_api_spec.md` 中回答相应端点、SSE 或幂等性规则。运行的 debug trace 会出现 `memory_context_injected`，证明本轮规划使用了检索到的 Markdown 知识。

## 边界

- 这是关键词/CJK 双字词检索，并会从命中文档中选取最相关的 Markdown 小节；它适合当前小规模规范库，提问中应保留规范中的关键名词或端点。
- 会话摘要用于压缩对话，不会替代文档检索。
- 为避免篡改人工维护的规范，自动写入默认且应保持关闭。
