#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

export APP_NAME=ktp-product
export APP_ENV=production
export APP_HOST=0.0.0.0
export APP_PORT=18080
export LOG_LEVEL=INFO
export APP_AUTH_ENABLED=true
export APP_AUTH_TOKEN=
export APP_JWT_SECRET=ktp-stable-jwt-secret-2024-a7f3b9c1e5d2
export V2_API_STORE_BACKEND=sqlite
export V2_API_SQLITE_PATH="$BACKEND_DIR/data/ktp_v2_runtime.sqlite3"
export AGENT_LLM_BACKEND=openai_compatible
export AGENT_LLM_OPENAI_API_BASE=http://127.0.0.1:8000/v1
export AGENT_LLM_OPENAI_API_KEY=EMPTY
export AGENT_LLM_OPENAI_MODEL_NAME="${AGENT_LLM_OPENAI_MODEL_NAME:-qwen-plus}"
export AGENT_LLM_REQUEST_TIMEOUT_SECONDS=180
export KTP_LICENSE_SKIP=1

mkdir -p "$BACKEND_DIR/data"

start_backend() {
    echo "启动后端服务..."
    cd "$BACKEND_DIR"
    uvicorn apps.api_gateway.main:app \
        --host 0.0.0.0 \
        --port 18080 \
        --timeout-keep-alive 30 \
        &
    BACKEND_PID=$!
    echo "后端服务已启动 (PID: $BACKEND_PID, 端口: 18080)"
}

start_frontend() {
    echo "启动前端服务..."
    cd "$FRONTEND_DIR/dist"
    python3 -m http.server 3002 \
        --bind 0.0.0.0 \
        &
    FRONTEND_PID=$!
    echo "前端服务已启动 (PID: $FRONTEND_PID, 端口: 3002)"
}

stop_services() {
    echo "停止服务..."
    [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null && echo "后端已停止"
    [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null && echo "前端已停止"
}

trap stop_services EXIT INT TERM

case "${1:-start}" in
    start)
        start_backend
        sleep 3
        start_frontend
        echo ""
        echo "========================================="
        echo "  KTP 服务已启动"
        echo "========================================="
        echo "  前端: http://localhost:3002"
        echo "  后端: http://localhost:18080"
        echo "  后端健康: http://localhost:18080/health"
        echo "========================================="
        echo ""
        echo "按 Ctrl+C 停止服务"
        wait
        ;;
    backend)
        start_backend
        wait
        ;;
    frontend)
        start_frontend
        wait
        ;;
    *)
        echo "用法: $0 [start|backend|frontend]"
        ;;
esac
