#!/bin/bash

# 导出当前环境的精确依赖版本
# 用于记录和复现部署环境

OUTPUT_FILE="environment_snapshot.txt"

echo "=========================================="
echo "  环境快照生成工具"
echo "=========================================="
echo ""
echo "正在生成环境快照到: $OUTPUT_FILE"
echo ""

{
    echo "# ROS Monitor 环境快照"
    echo "# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "# 主机名: $(hostname)"
    echo ""
    
    echo "## 系统信息"
    echo "操作系统: $(lsb_release -d | cut -f2)"
    echo "内核版本: $(uname -r)"
    echo "系统架构: $(uname -m)"
    echo ""
    
    echo "## 核心运行时版本"
    echo "Python: $(python3 --version 2>&1)"
    echo "pip: $(pip3 --version 2>&1 | cut -d' ' -f1,2)"
    
    if command -v node &> /dev/null; then
        echo "Node.js: $(node --version)"
        echo "npm: $(npm --version)"
    fi
    
    if [ ! -z "$ROS_DISTRO" ]; then
        echo "ROS: $ROS_DISTRO"
    fi
    echo ""
    
    echo "## Python包（虚拟环境）"
    if [ -d "ros_monitor_backend/.venv" ]; then
        source ros_monitor_backend/.venv/bin/activate
        pip freeze
        deactivate
    else
        echo "虚拟环境不存在"
    fi
    echo ""
    
    echo "## Node.js包"
    if [ -f "ros_monitor_frontend/package-lock.json" ]; then
        cd ros_monitor_frontend
        npm list --depth=0 2>/dev/null || echo "npm依赖未安装"
        cd ..
    else
        echo "package-lock.json不存在"
    fi
    echo ""
    
    echo "## 系统包（ROS相关）"
    if command -v dpkg &> /dev/null; then
        dpkg -l | grep ros-$ROS_DISTRO | awk '{print $2, $3}' || echo "无ROS包"
    fi
    echo ""
    
    echo "## 环境变量"
    echo "ROS_MASTER_URI: ${ROS_MASTER_URI:-未设置}"
    echo "ROS_HOSTNAME: ${ROS_HOSTNAME:-未设置}"
    echo "ROS_IP: ${ROS_IP:-未设置}"
    echo "PYTHONPATH: ${PYTHONPATH:-未设置}"
    echo ""
    
} > "$OUTPUT_FILE"

echo "✓ 环境快照已生成: $OUTPUT_FILE"
echo ""
echo "使用方法："
echo "  1. 查看快照: cat $OUTPUT_FILE"
echo "  2. 在新环境中对比: diff $OUTPUT_FILE <new_snapshot>"
echo "  3. 作为部署参考文档"
