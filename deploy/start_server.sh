#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${KTP_BASE_DIR:-/data/yuehao/apps/ktp}"
APP_DIR="$BASE_DIR/app"
BACKEND_DIR="$APP_DIR/backend"
PYTHON_BIN="${KTP_PYTHON_BIN:-/data/yuehao/conda-envs/ktp-prod/bin/python}"
LOG_DIR="$BASE_DIR/logs"
RUN_DIR="$BASE_DIR/run"

mkdir -p "$LOG_DIR" "$RUN_DIR"

start_process() {
    local name="$1"
    shift
    local pid_file="$RUN_DIR/$name.pid"
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "$name is already running (PID $(cat "$pid_file"))"
        return
    fi
    nohup "$@" >"$LOG_DIR/$name.log" 2>&1 &
    echo "$!" >"$pid_file"
    echo "started $name (PID $!)"
}

cd "$BACKEND_DIR"
set -a
# shellcheck disable=SC1091
source .env
set +a

start_process backend "$PYTHON_BIN" -m uvicorn apps.api_gateway.main:app \
    --host 0.0.0.0 --port 8005 --timeout-keep-alive 30

export BACKEND_URL="http://127.0.0.1:8005"
export FRONTEND_PORT="3002"
start_process frontend "$PYTHON_BIN" "$APP_DIR/deploy/serve_frontend.py"
