# KTP 前端文档

> 版本: 0.2.0 | React + TypeScript + Vite

---

## 快速开始

### 安装依赖

```bash
cd ktp/frontend/
npm install
```

### 启动开发服务器

```bash
npm run dev
```

前端默认运行在 `http://localhost:3000`，代理到后端 `http://localhost:18180`。

### 构建生产版本

```bash
npm run build
```

---

## 页面说明

### ChatPage (`/v2/ui`)

主聊天界面，用于与多智能体系统进行自然语言交互。

**功能：**
- 发送消息与 Agent 对话
- 查看对话历史
- 上传遥感影像文件
- 流式响应显示

**API 端点：** `/v2/chat`

---

### AnalysisPage (`/v2/ui/analysis`)

遥感影像分析页面。

**功能：**
- 上传遥感影像（.tif 等格式）
- 选择分析模型（秃斑检测、LAI 反演等）
- 查看分析结果和置信度地图

**API 端点：** `/v2/detect`

---

### DatasetsPage (`/v2/ui/datasets`)

数据集管理页面。

**功能：**
- 浏览已上传的数据集
- 查看数据集元数据
- 下载数据集

---

### HistoryPage (`/v2/ui/history`)

对话历史页面。

**功能：**
- 查看所有历史对话
- 搜索历史消息
- 重新加载历史对话

---

### ResultsPage (`/v2/ui/results`)

分析结果页面。

**功能：**
- 查看历史分析结果
- 可视化展示（图表、地图）
- 导出报告

---

### SettingsPage (`/v2/ui/settings`)

系统设置页面。

**功能：**
- LLM 提供者配置
- API 密钥设置
- 模型参数调整
- 系统偏好设置

---

### SkillsPage (`/v2/ui/skills`)

技能管理页面。

**功能：**
- 浏览可用技能
- 查看技能详情
- 启用/禁用技能

---

## 组件库

### 通用组件

| 组件 | 说明 |
|------|------|
| `MessageBubble` | 聊天消息气泡 |
| `FileUpload` | 文件上传组件 |
| `ImagePreview` | 遥感影像预览 |
| `ConfidenceMap` | 置信度地图 |
| `LoadingSpinner` | 加载指示器 |

---

## 服务层

API 客户端位于 `src/services/` 目录：

```
src/services/
├── api.ts           # 主 API 客户端
├── chat.ts          # 聊天 API
├── analysis.ts      # 分析 API
└── storage.ts       # 本地存储
```

### 使用示例

```typescript
import { chatApi } from '@/services/chat';

const response = await chatApi.send({
  message: '分析这张遥感影像',
  session_id: 'session-001'
});
```

---

## 类型定义

类型定义位于 `src/types/` 目录：

```typescript
// 消息类型
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

// 分析结果
interface AnalysisResult {
  id: string;
  model: string;
  status: 'pending' | 'completed' | 'failed';
  result?: any;
}
```
