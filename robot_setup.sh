#!/bin/bash
# ============================================================
# 机器人端部署脚本（推送模式）
# 机器人运行 robot_agent.py，主动连接服务器上报数据
# 服务器 IP 固定，机器人端无需知道自己的 IP
# ============================================================

set -e

echo "============================================"
echo "  ROS Monitor 机器人端部署（推送模式）"
echo "============================================"
echo ""

# ---- 配置 ----
SERVER_URL="${SERVER_URL:-ws://43.136.76.169:801}"
ROBOT_ID="${ROBOT_ID:-$(hostname)}"

# 1. 检查 ROS 环境
if [ -z "$ROS_DISTRO" ]; then
    echo "加载 ROS 环境..."
    if [ -f "/opt/ros/noetic/setup.bash" ]; then
        source /opt/ros/noetic/setup.bash
    elif [ -f "/opt/ros/melodic/setup.bash" ]; then
        source /opt/ros/melodic/setup.bash
    else
        echo "错误: 未找到 ROS 安装，请先安装 ROS"
        exit 1
    fi
fi
echo "ROS $ROS_DISTRO 已加载"

# 2. 检查 Python websocket-client
echo ""
echo "检查 Python 依赖..."
if ! python3 -c "import websocket" 2>/dev/null; then
    echo "安装 websocket-client..."
    pip3 install websocket-client
fi
echo "依赖就绪"

# 3. 获取本机 IP
get_ip() {
    local ip=$(ip route get 1.2.3.4 2>/dev/null | awk '{print $7}' | head -n1)
    if [ -z "$ip" ]; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    echo "${ip:-unknown}"
}

ROBOT_IP=$(get_ip)
echo ""
echo "============================================"
echo "  机器人信息"
echo "============================================"
echo "  IP:        $ROBOT_IP"
echo "  ID:        $ROBOT_ID"
echo "  服务器:    $SERVER_URL"
echo ""

# 4. 启动指令
echo "============================================"
echo "  请按以下顺序启动："
echo "============================================"
echo ""
echo "  终端 1 - ROS Master:"
echo "    roscore"
echo ""
echo "  终端 2 - 传感器驱动 (以 Mid-360 为例):"
echo "    source ~/catkin_ws/devel/setup.bash"
echo "    roslaunch livox_ros_driver livox_lidar.launch"
echo ""
echo "  终端 3 - 数据推送代理:"
echo "    source <你的ROS工作空间>/devel/setup.bash"
echo "    python3 robot_agent.py --server $SERVER_URL --robot-id $ROBOT_ID"
echo ""
echo "  机器人将自动连接服务器并推送数据，无需 rosbridge！"
echo "============================================"
echo ""

# 5. 启动 agent
if [ "${AUTO_START}" = "1" ]; then
    echo "自动启动数据推送代理..."
    exec python3 robot_agent.py --server "$SERVER_URL" --robot-id "$ROBOT_ID"
fi
