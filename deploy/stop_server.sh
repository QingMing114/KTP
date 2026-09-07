#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${KTP_BASE_DIR:-/data/yuehao/apps/ktp}"
RUN_DIR="$BASE_DIR/run"

for name in frontend backend; do
    pid_file="$RUN_DIR/$name.pid"
    if [[ ! -f "$pid_file" ]]; then
        echo "$name is not running"
        continue
    fi
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        echo "stopped $name (PID $pid)"
    else
        echo "$name PID file was stale"
    fi
    rm -f "$pid_file"
done
