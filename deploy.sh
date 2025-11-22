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
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ 已创建 .env 文件"
        echo "⚠️  请编辑 .env 文件配置您的环境"
        echo "   主要配置项："
        echo "   - ROS_MASTER_URI: ROS Master地址"
        echo "   - ROS_IP: 本机IP地址"
        echo "   - VITE_API_HOST: 前端访问后端的地址"
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

# 6. 验证ROS环境
echo "=== 步骤 6: 验证ROS环境 ==="
if [ -z "$ROS_DISTRO" ]; then
    echo "⚠️  ROS环境未加载"
    if [ -f "/opt/ros/noetic/setup.bash" ]; then
        echo "   请运行: source /opt/ros/noetic/setup.bash"
    elif [ -f "/opt/ros/melodic/setup.bash" ]; then
        echo "   请运行: source /opt/ros/melodic/setup.bash"
    else
        echo "   ROS未安装，请访问: http://wiki.ros.org/noetic/Installation/Ubuntu"
    fi
else
    echo "✓ ROS环境已加载: $ROS_DISTRO"
fi
echo ""

# 7. 完成
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "下一步操作："
echo ""
echo "1. 配置环境变量（如果还未配置）："
echo "   vim .env"
echo ""
echo "2. 确保ROS环境已加载："
echo "   source /opt/ros/noetic/setup.bash"
echo ""
echo "3. 启动后端服务："
echo "   cd ros_monitor_backend"
echo "   ./start_backend.sh"
echo ""
echo "4. 启动前端服务（新终端）："
echo "   cd ros_monitor_frontend"
echo "   ./start_frontend.sh"
echo ""
echo "5. 访问系统："
echo "   http://localhost:5173"
echo ""
echo "📚 更多信息请参考："
echo "   - environment.yml (环境规格文件)"
echo "   - .env (环境配置)"
echo "   - Documents/ (项目文档)"
echo ""
