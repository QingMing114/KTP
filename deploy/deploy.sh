#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "  KTP 产品部署脚本"
echo "========================================="
echo ""

check_docker() {
    if ! command -v docker &>/dev/null; then
        echo "ERROR: Docker 未安装，请先安装 Docker"
        exit 1
    fi
    if ! docker info &>/dev/null; then
        echo "ERROR: Docker 未启动，请先启动 Docker"
        exit 1
    fi
    if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null; then
        echo "ERROR: Docker Compose 未安装"
        exit 1
    fi
}

generate_license() {
    local customer="${1:-demo}"
    local days="${2:-365}"
    echo "生成许可证: 客户=${customer}, 有效期=${days}天"
    docker run --rm -v "${SCRIPT_DIR}/license.key:/app/data/license.key" \
        "$(docker build -q -f ../backend/Dockerfile --target builder ../backend)" \
        python -c "from scripts.license_guard import generate_license; generate_license('${customer}', ${days})" 2>/dev/null || \
    python3 "${PROJECT_ROOT}/backend/scripts/license_guard.py" generate "${customer}" "${days}"
}

build_images() {
    echo "构建 Docker 镜像（源码编译为二进制）..."
    local compose_cmd="docker compose"
    if ! docker compose version &>/dev/null; then
        compose_cmd="docker-compose"
    fi

    cd "${SCRIPT_DIR}"
    ${compose_cmd} build --no-cache
    echo "镜像构建完成！"
}

start_services() {
    local compose_cmd="docker compose"
    if ! docker compose version &>/dev/null; then
        compose_cmd="docker-compose"
    fi

    cd "${SCRIPT_DIR}"
    ${compose_cmd} up -d
    echo ""
    echo "服务已启动！"
    echo "  前端: http://localhost:${FRONTEND_PORT:-3002}"
    echo "  后端: http://localhost:${BACKEND_PORT:-8005}"
    echo ""
    echo "查看日志: ${compose_cmd} logs -f"
    echo "停止服务: ${compose_cmd} down"
}

show_machine_id() {
    echo "当前机器ID:"
    python3 "${PROJECT_ROOT}/backend/scripts/license_guard.py" machine-id 2>/dev/null || \
    echo "(需要先部署后获取)"
}

case "${1:-help}" in
    build)
        check_docker
        build_images
        ;;
    start)
        check_docker
        start_services
        ;;
    stop)
        cd "${SCRIPT_DIR}"
        docker compose down 2>/dev/null || docker-compose down 2>/dev/null
        echo "服务已停止"
        ;;
    license)
        show_machine_id
        echo ""
        if [ -f "${SCRIPT_DIR}/license.key" ]; then
            echo "当前许可证状态:"
            python3 "${PROJECT_ROOT}/backend/scripts/license_guard.py" validate 2>/dev/null || echo "验证失败"
        else
            echo "许可证文件不存在"
            echo "生成许可证: $0 generate <客户名> [天数]"
        fi
        ;;
    generate)
        check_docker
        generate_license "${2:-demo}" "${3:-365}"
        ;;
    deploy)
        check_docker
        build_images
        if [ ! -f "${SCRIPT_DIR}/license.key" ]; then
            echo "未找到许可证，生成试用许可证..."
            generate_license "trial" "30"
        fi
        start_services
        ;;
    machine-id)
        show_machine_id
        ;;
    help|*)
        echo "用法: $0 <命令>"
        echo ""
        echo "命令:"
        echo "  build       构建 Docker 镜像（源码编译为二进制）"
        echo "  start       启动服务"
        echo "  stop        停止服务"
        echo "  deploy      一键部署（构建+许可证+启动）"
        echo "  license     查看许可证状态"
        echo "  generate    生成许可证: $0 generate <客户名> [天数]"
        echo "  machine-id  查看机器ID"
        ;;
esac
