#!/bin/bash

# ROS Monitor 快速部署脚本
# 适用于全新环境的自动化部署

set -e

echo "=========================================="
echo "  ROS Monitor 快速部署脚本"
echo "=========================================="
echo ""

# 检查是否以root运行（某些操作需要）
if [ "$EUID" -eq 0 ]; then 
    echo "⚠️  请不要以root身份运行此脚本"
    echo "   某些步骤会使用sudo自动提权"
    exit 1
fi

# 1. 检查基础环境
echo "=== 步骤 1: 检查基础环境 ==="
./check_environment.sh || {
    echo ""
    echo "环境检查失败，是否继续安装缺失的依赖？[y/N]"
    read -r response
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "部署已取消"
        exit 1
    fi
}
echo ""

# 2. 安装系统依赖（如果需要）
echo "=== 步骤 2: 安装系统依赖 ==="
if ! command -v python3 &> /dev/null || ! command -v node &> /dev/null; then
    echo "是否安装系统依赖？[y/N]"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        sudo apt update
        sudo apt install -y build-essential python3 python3-pip python3-venv python3-dev \
            curl git net-tools lsof
        echo "✓ 系统依赖安装完成"
    fi
else
    echo "✓ 系统依赖已满足"
fi
echo ""

# 3. 配置环境变量
echo "=== 步骤 3: 配置环境变量 ==="
if [ ! -f ".env" ]; then
    if [ -f "ros_monitor_backend/.env.example" ]; then
        cp ros_monitor_backend/.env.example ros_monitor_backend/.env
        echo "✓ 已创建 .env 文件 (ros_monitor_backend/.env)"
        echo "⚠️  请编辑 .env 文件配置您的环境"
        echo "   主要配置项："
        echo "   - ROSBRIDGE_HOST: rosbridge 服务器地址（机器人IP）"
        echo "   - ROSBRIDGE_PORT: rosbridge 端口（默认 9090）"
    else
        echo "⚠️  .env.example 文件不存在，跳过"
    fi
else
    echo "✓ .env 文件已存在"
fi
echo ""

# 4. 安装后端依赖
echo "=== 步骤 4: 安装后端Python依赖 ==="
cd ros_monitor_backend

if [ ! -d ".venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv .venv
fi

echo "激活虚拟环境..."
source .venv/bin/activate

echo "安装Python依赖..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✓ 后端依赖安装完成"
deactivate
cd ..
echo ""

# 5. 安装前端依赖
echo "=== 步骤 5: 安装前端依赖 ==="
cd ros_monitor_frontend

if command -v npm &> /dev/null; then
    echo "安装Node.js依赖..."
    npm install
    echo "✓ 前端依赖安装完成"
else
    echo "⚠️  npm未安装，跳过前端依赖安装"
    echo "   请先安装Node.js: https://nodejs.org/"
fi

cd ..
echo ""

# 6. 检查 rosbridge 配置
echo "=== 步骤 6: 检查 rosbridge 配置 ==="
echo "后端使用 rosbridge WebSocket 远程连接机器人 ROS 系统"
echo ""
echo "机器人端需要:"
echo "  1. 安装 rosbridge: sudo apt-get install ros-<distro>-rosbridge-suite"
echo "  2. 启动: roslaunch rosbridge_server rosbridge_websocket.launch"
echo ""
echo "服务器端配置:"
echo "  编辑 ros_monitor_backend/.env"
echo "  ROSBRIDGE_HOST=<机器人IP>"
echo ""
echo ""

# 7. 完成
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "下一步操作："
echo ""
echo "1. 配置 rosbridge 连接地址："
echo "   vim ros_monitor_backend/.env"
echo "   (设置 ROSBRIDGE_HOST=机器人IP)"
echo ""
echo "2. 启动后端服务："
echo "   cd ros_monitor_backend"
echo "   ./start_backend.sh"
echo ""
echo "3. 启动前端服务（新终端）："
echo "   cd ros_monitor_frontend"
echo "   npm run dev"
echo ""
echo "4. 访问系统："
echo "   http://localhost:5173"
echo ""
