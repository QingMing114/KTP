# AgentLLMConfig 配置文档

## 概述

`AgentLLMConfig` 是规划器/执行器本地 LLM 集成的运行时配置类，基于 Pydantic Settings 实现，支持从环境变量读取配置。

## 配置参数详解

### 1. 上下文窗口配置

#### context_window_tokens

- **说明**: 模型的上下文窗口大小（以 token 为单位）
- **默认值**: 32768
- **环境变量**: `AGENT_LLM_CONTEXT_WINDOW_TOKENS`

#### context_reserve_output_tokens

- **说明**: 为模型输出保留的 token 数量
- **默认值**: 2048
- **环境变量**: `AGENT_LLM_CONTEXT_RESERVE_OUTPUT_TOKENS`

#### context_history_messages

- **说明**: 保留在上下文历史中的消息数量
- **默认值**: 20
- **环境变量**: `AGENT_LLM_CONTEXT_HISTORY_MESSAGES`

#### context_message_max_chars

- **说明**: 单条消息的最大字符数限制
- **默认值**: 300
- **环境变量**: `AGENT_LLM_CONTEXT_MESSAGE_MAX_CHARS`

### 2. Token 计算公式

#### 可用输入 Token 数

$$T_{available} = T_{context} - T_{reserve} - T_{output}$$

其中：
- $T_{available}$: 可用于输入的 token 数
- $T_{context}$: `context_window_tokens`
- $T_{reserve}$: `context_reserve_output_tokens`
- $T_{output}$: `max_new_tokens`

**实际应用示例**：

当 `context_window_tokens = 32768`，`context_reserve_output_tokens = 2048`，`max_new_tokens = 2048` 时：

$$T_{available} = 32768 - 2048 - 2048 = 28672$$

#### 历史消息 Token 预算

单轮对话的历史消息 token 预算：

$$T_{history} = T_{available} - T_{current\_input}$$

其中 $T_{current\_input}$ 是当前输入消息的 token 数。

平均每条历史消息的 token 分配：

$$T_{avg\_per\_msg} = \frac{min(T_{history}, N_{msg} \times C_{max})}{N_{msg}}$$

其中：
- $N_{msg}$: `context_history_messages`
- $C_{max}$: `context_message_max_chars`（按字符估算，约 1 token ≈ 4 字符）

### 3. 生成参数

#### max_new_tokens

- **说明**: 单次生成的最大 token 数量
- **默认值**: 2048
- **环境变量**: `AGENT_LLM_MAX_NEW_TOKENS`

#### structured_max_new_tokens

- **说明**: 结构化输出（如 JSON）的最大 token 数
- **默认值**: 384
- **环境变量**: `AGENT_LLM_STRUCTURED_MAX_NEW_TOKENS`

#### chat_max_new_tokens

- **说明**: 聊天模式的最大 token 数
- **默认值**: 256
- **环境变量**: `AGENT_LLM_CHAT_MAX_NEW_TOKENS`

#### temperature

- **说明**: 生成温度，控制随机性
- **默认值**: 0.0
- **范围**: 通常 0.0 - 2.0
- **环境变量**: `AGENT_LLM_TEMPERATURE`

#### top_p

- **说明**: Nucleus sampling 的概率阈值
- **默认值**: 0.9
- **环境变量**: `AGENT_LLM_TOP_P`

### 4. 重试配置

#### openai_max_retries

- **说明**: API 请求的最大重试次数
- **默认值**: 2
- **环境变量**: `AGENT_LLM_OPENAI_MAX_RETRIES`

#### openai_retry_backoff_seconds

- **说明**: 重试间隔的退避时间（秒）
- **默认值**: 1.0
- **环境变量**: `AGENT_LLM_OPENAI_RETRY_BACKOFF_SECONDS`

#### 请求超时计算

总请求超时时间：

$$T_{total} = T_{request} + N_{retries} \times T_{backoff}$$

其中：
- $T_{request}$: `request_timeout_seconds`
- $N_{retries}$: `openai_max_retries`
- $T_{backoff}$: `openai_retry_backoff_seconds`

**示例**（默认值）：

$$T_{total} = 45.0 + 2 \times 1.0 = 47.0 \text{ 秒}$$

### 5. Agent 行为配置

#### agent_max_steps

- **说明**: Agent 最大执行步数
- **默认值**: 20
- **环境变量**: `AGENT_LLM_AGENT_MAX_STEPS`

#### allow_fallback

- **说明**: 是否允许降级到启发式方法
- **默认值**: True
- **环境变量**: `AGENT_LLM_ALLOW_FALLBACK`

#### planner_enabled

- **说明**: 是否启用规划器
- **默认值**: True
- **环境变量**: `AGENT_LLM_PLANNER_ENABLED`

#### executor_enabled

- **说明**: 是否启用执行器
- **默认值**: True
- **环境变量**: `AGENT_LLM_EXECUTOR_ENABLED`

### 6. 设备配置

#### cuda_visible_devices

- **说明**: 指定可见的 CUDA 设备
- **默认值**: None（使用所有设备）
- **环境变量**: `AGENT_LLM_CUDA_VISIBLE_DEVICES`

#### device_map

- **说明**: 模型在多设备间的分配策略
- **默认值**: "auto"
- **环境变量**: `AGENT_LLM_DEVICE_MAP`

#### require_accelerator

- **说明**: 是否要求加速器（GPU）
- **默认值**: True
- **环境变量**: `AGENT_LLM_REQUIRE_ACCELERATOR`

## 环境变量配置示例

```bash
# 核心配置
export AGENT_LLM_BACKEND="openai_compatible"
export AGENT_LLM_MODEL_PATH="/models/qwen"
export AGENT_LLM_OPENAI_API_BASE="http://127.0.0.1:8000/v1"
export AGENT_LLM_OPENAI_MODEL_NAME="qwen"

# 上下文配置
export AGENT_LLM_CONTEXT_WINDOW_TOKENS=32768
export AGENT_LLM_CONTEXT_RESERVE_OUTPUT_TOKENS=2048
export AGENT_LLM_CONTEXT_HISTORY_MESSAGES=20
export AGENT_LLM_CONTEXT_MESSAGE_MAX_CHARS=300

# 生成配置
export AGENT_LLM_MAX_NEW_TOKENS=2048
export AGENT_LLM_TEMPERATURE=0.0
export AGENT_LLM_TOP_P=0.9

# Agent 配置
export AGENT_LLM_AGENT_MAX_STEPS=20
export AGENT_LLM_PLANNER_ENABLED=true
export AGENT_LLM_EXECUTOR_ENABLED=true
```

## 架构约束公式

### Agent 步数与 Token 预算关系

整个 Agent 执行的 token 预算：

$$T_{agent} = T_{available} \times N_{steps}$$

其中 $N_{steps}$ 是 `agent_max_steps`。

**示例**：

$$T_{agent} = 28672 \times 20 = 573440 \text{ tokens}$$

### 内存估算（简化模型）

推理内存需求近似：

$$M \approx P \times 4 \text{ bytes}$$

其中 $P$ 是模型参数量（以 B 为单位）。

## 配置验证

获取配置实例：

```python
from ktp.backend.infra.llm.config import get_agent_llm_config

config = get_agent_llm_config()
```

配置会被缓存（`lru_cache`），确保同一进程内只加载一次。
