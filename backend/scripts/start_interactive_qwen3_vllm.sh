#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${QWEN3_INTERACTIVE_MODEL_PATH:-/home/D/yuanshuai/.cache/modelscope/hub/models/Qwen/Qwen3.5-27B}"
HOST="${QWEN3_INTERACTIVE_HOST:-0.0.0.0}"
PORT="${QWEN3_INTERACTIVE_PORT:-8001}"
TENSOR_PARALLEL_SIZE="${QWEN3_INTERACTIVE_TP:-4}"
GPU_MEMORY_UTILIZATION="${QWEN3_INTERACTIVE_GPU_MEMORY_UTILIZATION:-0.85}"
MAX_MODEL_LEN="${QWEN3_INTERACTIVE_MAX_MODEL_LEN:-32768}"
VLLM_BIN="${QWEN3_INTERACTIVE_VLLM_BIN:-/home/D/yuanshuai/miniconda3/envs/vllm/bin/vllm}"

if [[ ! -x "${VLLM_BIN}" ]]; then
  echo "vLLM executable not found: ${VLLM_BIN}" >&2
  exit 1
fi

exec "${VLLM_BIN}" serve "${MODEL_PATH}" \
  --port "${PORT}" \
  --host "${HOST}" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --enforce-eager \
  --reasoning-parser qwen3 \
  --language-model-only
