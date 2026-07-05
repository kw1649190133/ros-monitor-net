#!/bin/bash

# ROS监控后端启动脚本（rosbridge 版）
# 后端通过 rosbridge WebSocket 远程连接机器人，无需本地 ROS 环境

set -e

echo "=== ROS监控后端启动脚本（rosbridge）==="

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv .venv
    echo "虚拟环境创建完成"
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source .venv/bin/activate

# 检查依赖
echo "检查Python依赖..."
if ! pip show fastapi > /dev/null 2>&1; then
    echo "安装Python依赖..."
    pip install -r requirements.txt
    echo "依赖安装完成"
else
    echo "依赖已安装"
fi

# rosbridge 配置
export ROSBRIDGE_HOST=${ROSBRIDGE_HOST:-"localhost"}
export ROSBRIDGE_PORT=${ROSBRIDGE_PORT:-"9090"}

echo "rosbridge 连接目标: ws://${ROSBRIDGE_HOST}:${ROSBRIDGE_PORT}"

# 验证 rosbridge 是否可达
echo "检查 rosbridge 连接..."
if python3 -c "
import socket, sys
s = socket.socket()
s.settimeout(3)
try:
    s.connect(('${ROSBRIDGE_HOST}', ${ROSBRIDGE_PORT}))
    s.close()
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
    echo "rosbridge 端口可达 (${ROSBRIDGE_HOST}:${ROSBRIDGE_PORT})"
else
    echo "============================================"
    echo "  警告: rosbridge 端口不可达"
    echo "  请确保机器人端已运行:"
    echo "    roslaunch rosbridge_server rosbridge_websocket.launch"
    echo "============================================"
    echo ""
    echo "后端将继续启动，连接将在 rosbridge 可用后自动建立"
fi

# 设置环境变量
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 设置默认端口
export ROS_MONITOR_PORT=${ROS_MONITOR_PORT:-8001}

echo "环境配置:"
echo "  - ROSBRIDGE_HOST: $ROSBRIDGE_HOST"
echo "  - ROSBRIDGE_PORT: $ROSBRIDGE_PORT"
echo "  - ROS_MONITOR_PORT: $ROS_MONITOR_PORT"

# 查找可用端口
find_free_port() {
    local port=${ROS_MONITOR_PORT:-8001}
    while netstat -tuln 2>/dev/null | grep -q ":$port "; do
        echo "  端口 $port 已被占用"
        port=$((port + 1))
        if [ $port -gt 8100 ]; then
            echo "  找不到可用端口 (8001-8100)"
            exit 1
        fi
    done
    echo $port
}

PORT=$(find_free_port)
echo "使用端口: $PORT"

echo ""
echo "启动ROS监控后端服务..."
echo "  访问地址: http://localhost:$PORT"
echo "  API文档:  http://localhost:$PORT/docs"
echo "  按 Ctrl+C 停止服务"
echo ""

python3 -m src.main --port $PORT
