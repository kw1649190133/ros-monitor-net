#!/bin/bash

# ROS监控后端启动脚本
# 需要在虚拟环境下运行
#
# GNSS功能说明:
# - gnss_comm是香港科技大学(HKUST-Aerial-Robotics)维护的GNSS消息包
# - 必须从源码克隆并编译安装,无法通过apt-get安装
# - 需要source ublox_ws/devel/setup.bash才能使用/ublox_driver/receiver_pvt话题
# - 可用话题: /ublox_driver/receiver_pvt (gnss_comm/GnssPVTSolnMsg)
#              /ublox_driver/receiver_lla (sensor_msgs/NavSatFix)

set -e

echo "=== ROS监控后端启动脚本 ==="

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 虚拟环境不存在，正在创建..."
    python3 -m venv .venv
    echo "✅ 虚拟环境创建完成"
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source .venv/bin/activate

# 检查依赖
echo "📦 检查Python依赖..."
if ! pip show fastapi > /dev/null 2>&1; then
    echo "📥 安装Python依赖..."
    pip install -r requirements.txt
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已安装"
fi

# 检查ROS环境
echo "🤖 检查ROS环境..."
if [ -z "$ROS_DISTRO" ]; then
    echo "⚠️  ROS环境未加载，尝试加载..."
    if [ -f "/opt/ros/noetic/setup.bash" ]; then
        source /opt/ros/noetic/setup.bash
        echo "✅ ROS Noetic环境已加载"
    elif [ -f "/opt/ros/melodic/setup.bash" ]; then
        source /opt/ros/melodic/setup.bash
        echo "✅ ROS Melodic环境已加载"
    else
        echo "❌ 未找到ROS环境，请手动加载"
        exit 1
    fi
else
    echo "✅ ROS环境已加载: $ROS_DISTRO"
fi

# 检查IKing Handbot工作空间
if [ -f "/home/ycs/work/ikinghandbot/devel/setup.bash" ]; then
    echo "🏠 加载IKing Handbot工作空间..."
    source /home/ycs/work/ikinghandbot/devel/setup.bash
    echo "✅ 工作空间已加载"
else
    echo "⚠️  IKing Handbot工作空间未找到，跳过..."
fi

# 检查并加载GNSS ublox工作空间 (gnss_comm必须通过源码编译)
if [ -f "/home/ycs/work/ublox_ws/devel/setup.bash" ]; then
    echo "📡 加载GNSS ublox工作空间..."
    source /home/ycs/work/ublox_ws/devel/setup.bash
    echo "✅ GNSS工作空间已加载 (gnss_comm可用)"
    
    # 验证gnss_comm是否可用
    if python3 -c "from gnss_comm.msg import GnssPVTSolnMsg" 2>/dev/null; then
        echo "✅ gnss_comm消息类型验证成功"
    else
        echo "⚠️  gnss_comm导入失败，GNSS功能可能不可用"
    fi
else
    echo "⚠️  GNSS ublox工作空间未找到 (/home/ycs/work/ublox_ws)"
    echo "   GNSS/RTK功能将不可用，系统将继续运行其他传感器"
fi

# 设置环境变量
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export ROS_MASTER_URI=${ROS_MASTER_URI:-"http://localhost:11311"}
export ROS_HOSTNAME=${ROS_HOSTNAME:-"localhost"}

# 设置默认端口为8001
export ROS_MONITOR_PORT=${ROS_MONITOR_PORT:-8001}

echo "🌐 环境配置:"
echo "  - ROS_MASTER_URI: $ROS_MASTER_URI"
echo "  - ROS_HOSTNAME: $ROS_HOSTNAME"
echo "  - PYTHONPATH: $PYTHONPATH"
echo "  - ROS_MONITOR_PORT: $ROS_MONITOR_PORT"

# 强制终止占用端口的进程
kill_port_process() {
    local port=$1
    echo "🔍 检查端口 $port 是否被占用..."
    
    # 使用 netstat 查找占用端口的进程
    if netstat -tuln | grep :$port > /dev/null 2>&1; then
        echo "⚠️  端口 $port 被占用，正在查找占用进程..."
        
        # 尝试多种方式获取PID
        PIDS=$(lsof -ti :$port 2>/dev/null || netstat -tulnp 2>/dev/null | grep :$port | awk '{print $NF}' | cut -d'/' -f1 | grep -E '^[0-9]+$' | head -n 1)
        
        if [ ! -z "$PIDS" ]; then
            echo "🛑 终止占用端口的进程: $PIDS"
            kill -9 $PIDS 2>/dev/null || echo "⚠️  无法终止某些进程"
            sleep 2
        else
            echo "⚠️  无法确定占用端口的进程PID"
        fi
    else
        echo "✅ 端口 $port 未被占用"
    fi
}

# 查找可用端口的函数
find_free_port() {
    local port=${ROS_MONITOR_PORT:-8001}  # 使用环境变量或默认8001
    while netstat -tuln | grep :$port > /dev/null 2>&1; do
        echo "⚠️  端口$port已被占用"
        port=$((port + 1))
        if [ $port -gt 8100 ]; then
            echo "❌ 找不到可用端口 (${ROS_MONITOR_PORT:-8001}-8100)"
            exit 1
        fi
    done
    echo $port
}

# 清理常用端口（可选）
kill_port_process 8000
kill_port_process 8001

# 查找可用端口
PORT=$(find_free_port)
echo "✅ 使用端口: $PORT"

# 启动后端服务
echo "🚀 启动ROS监控后端服务..."
echo "   访问地址: http://localhost:$PORT"
echo "   API文档: http://localhost:$PORT/docs"
echo "   按 Ctrl+C 停止服务"

python3 -m src.main --port $PORT