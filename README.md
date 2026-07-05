# ROS Monitor (ros-monitor-net)

基于 FastAPI + React 的多传感器融合远程监控平台。支持激光雷达、IMU、相机、GNSS/RTK 等传感器数据的实时可视化，机器人端通过 WebSocket 主动推送数据到服务器，适配 WiFi / 移动网络等动态 IP 场景。

## 🚀 项目特性

- **实时数据监控**: ROS1 / ROS2 话题实时采集和可视化
- **多传感器支持**: 激光雷达、IMU、相机、GNSS/RTK、SLAM 轨迹与点云地图
- **推送架构**: 机器人主动连接服务器上报数据，无需固定 IP 或端口映射
- **WebSocket 通信**: 实时双向数据推送
- **现代化前端**: React + TypeScript + Ant Design + Three.js 3D 点云
- **RESTful API**: 完整后端 API + Swagger 文档
- **模拟测试**: 提供 mock_robot_test.py 无 ROS 环境下模拟数据验证

## 🏗️ 系统架构

```
┌─────────────────────┐                    ┌──────────────────────┐
│   机器人端 (ROS)      │   WebSocket 推送    │   服务器端             │
│                      │ ════════════════►  │                      │
│  robot_agent.py      │   ws://server/     │  FastAPI (:801)      │
│  (rospy 订阅话题)     │   ws/robot/{id}    │  + Nginx (:80)       │
│                      │                    │  + 前端静态文件        │
│  robot_agent_ros2.py │                    │                      │
│  (rclpy 订阅话题)     │                    │  浏览器               │
│                      │                    │  http://server/      │
│  传感器驱动           │                    │  /ros-monitor/       │
│  + livox_ros_driver  │                    │                      │
└─────────────────────┘                    └──────────────────────┘
```

**数据流**: 机器人 `robot_agent` → WebSocket → 服务器 `latest_data` → `background_broadcast` → 浏览器

**备选模式**: 也支持传统 rosbridge 模式（服务器主动连接机器人 rosbridge_server），详见 `.env` 配置。

## 📁 项目结构

```
ros-monitor/
├── ros_monitor_backend/          # FastAPI 后端
│   ├── src/
│   │   ├── main.py               # 入口：WebSocket 端点 + 广播
│   │   ├── ros_bridge/
│   │   │   ├── rosbridge_client.py   # rosbridge WebSocket 客户端
│   │   │   ├── pointcloud_parser.py  # PointCloud2 二进制解析
│   │   │   └── node_manager.py       # 话题订阅与数据管理
│   │   ├── api/v1/               # REST API 路由
│   │   ├── websocket/            # 浏览器连接管理
│   │   └── utils/                # 工具函数
│   ├── config/                   # YAML 配置文件
│   ├── .env.example              # 环境变量模板
│   └── requirements.txt          # Python 依赖
├── ros_monitor_frontend/         # React 前端
│   └── src/
├── robot_agent.py                # 机器人端代理 (ROS1)
├── robot_agent_ros2.py           # 机器人端代理 (ROS2)
├── mock_robot_test.py            # 模拟机器人测试脚本
├── robot_setup.sh                # 机器人端部署指引
├── deploy.sh                     # 服务器端部署脚本
├── start_monitor_system.sh       # 一键启动脚本 (本地开发)
└── README.md
```

## 🛠️ 技术栈

### 后端
- **FastAPI**: Python Web 框架 + Uvicorn
- **roslibpy**: rosbridge WebSocket 客户端（备选模式）
- **OpenCV / NumPy**: 图像与数据处理

### 前端
- **React 19 + TypeScript**: 前端框架
- **Ant Design**: UI 组件库
- **Three.js** (react-three-fiber): 3D 点云与轨迹可视化
- **Zustand**: 轻量级状态管理

### 机器人端
- **robot_agent.py**: rospy (ROS1)
- **robot_agent_ros2.py**: rclpy (ROS2) + websocket-client
- 无需 rosbridge，直接 WebSocket 推送

## 📦 快速开始

### 环境要求
- 服务器: Python 3.8+、Node.js 18+（无需 ROS）
- 机器人: ROS1 (rospy) 或 ROS2 (rclpy) + websocket-client
- 浏览器: 现代浏览器

### 步骤 1: 服务器端部署

```bash
# 克隆项目
git clone https://github.com/kw1649190133/ros-monitor-net.git
cd ros-monitor-net

# 部署（安装 Python/Node 依赖）
./deploy.sh

# 配置
cp ros_monitor_backend/.env.example ros_monitor_backend/.env
# 无需修改 .env（推送模式下不需要 ROSBRIDGE_HOST）

# 启动后端
cd ros_monitor_backend && ./start_backend.sh   # 或: systemctl start ros-monitor-backend

# 构建前端
cd ../ros_monitor_frontend
npm install && npm run build

# 部署到 Nginx
# 参考 deploy.sh 中的 Nginx 配置示例
```

### 步骤 2: 机器人端启动

**ROS1:**
```bash
pip install websocket-client
source /opt/ros/noetic/setup.bash
python3 robot_agent.py --server ws://<服务器IP> --robot-id myrobot
```

**ROS2:**
```bash
pip install sensor-msgs-py websocket-client
source /opt/ros/humble/setup.bash
python3 robot_agent_ros2.py --server ws://<服务器IP> --robot-id myrobot
```

机器人启动后，前端健康检查显示 `ros_ready: true` 即连接成功。

### 步骤 3: 模拟测试（无 ROS 环境）

```bash
pip install websocket-client numpy opencv-python
python mock_robot_test.py --server <服务器IP> --robot-id test-bot
```

生成模拟的 LiDAR 点云、IMU、相机、GNSS、SLAM 轨迹数据推送到服务器，验证端到端管道。

### 步骤 4: 访问系统

打开浏览器访问 `http://<服务器IP>/ros-monitor/`。

### 已部署实例

- **服务器**: 43.136.76.169
- **前端**: http://43.136.76.169/ros-monitor/
- **API 健康检查**: http://43.136.76.169/api/v1/health

## 🔧 配置说明

### 概念

项目支持两种数据接入模式：

| 模式 | 方向 | 适用场景 | 配置 |
|------|------|----------|------|
| **推送模式**（默认） | 机器人 → 服务器 | 机器人 IP 不固定 | 默认，无需配置 |
| **rosbridge 模式**（备选） | 服务器 → 机器人 | 机器人 IP 固定，需精细控制 | 设置 `ROSBRIDGE_HOST` |

### 环境变量 (.env)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ROSBRIDGE_HOST` | rosbridge 服务器地址（备选模式） | localhost |
| `ROSBRIDGE_PORT` | rosbridge 端口（备选模式） | 9090 |
| `ROS_MONITOR_PORT` | 后端服务端口 | 8001 |

### 后端
- 默认端口: 8001
- WebSocket 端点:
  - `/ws/robot/{robot_id}` — 机器人数据上报
  - `/ws/{client_id}` — 浏览器客户端
- API 文档: `http://localhost:8001/docs`
- 配置文件: `ros_monitor_backend/config/`

### 机器人端参数

```
--server   服务器地址（默认: ws://43.136.76.169，走 80 端口 Nginx 代理）
--robot-id 机器人标识（默认: 主机名）
```

### 前端
- 开发端口: 5173
- 构建: `npm run build`，输出 `dist/`
- 自动检测 API 地址（与浏览器同源）

## 📊 订阅话题

### LiDAR
- 话题: `/livox/lidar` (sensor_msgs/PointCloud2)
- 每帧最多采样 5000 个点 (x/y/z)
- 支持 Livox Mid-360 / Mid-70 等

### IMU
- 话题: `/livox/imu` (sensor_msgs/Imu)

### 相机
- 话题: `/left_camera/image/compressed`, `/rgb_img/compressed` (CompressedImage)
- 可通过 `config/camera_topics.yaml` 配置

### GNSS / RTK
- 话题: `/ublox_driver/receiver_lla` (NavSatFix)
- 兼容: `/ublox_driver/receiver_pvt` (GnssPVTSolnMsg)

### SLAM
- 轨迹: `/path` (nav_msgs/Path)
- 里程计: `/aft_mapped_to_init` (nav_msgs/Odometry)
- 配准点云: `/cloud_registered` (sensor_msgs/PointCloud2)

## 🧪 测试

### 模拟机器人
```bash
python mock_robot_test.py --server 43.136.76.169 --robot-id test-bot
```

### 后端测试
```bash
cd ros_monitor_backend
python -m pytest tests/
```

### 前端测试
```bash
cd ros_monitor_frontend
npm run lint
```

## 🚨 常见问题

### 连接被拒绝 (403)
1. 确认使用端口 80 而非 801（外网只开放 80）: `--server ws://<IP>` 不带端口号
2. 确认后端已更新到包含 `robot_websocket_endpoint` 的版本
3. 检查服务器: `curl http://<IP>/api/v1/health`，确认 `ros_ready: true`

### 前端 3D 点云不显示
1. 点击左侧菜单 "LiDAR" 进入点云页面
2. 确认机器人端已发布话题数据
3. 首次连接需等待约 3-5 秒数据累积

### 后端启动失败（端口被占用）
```bash
# 查看占用进程
lsof -i :801
# 强制释放后重启
kill $(lsof -ti :801) && systemctl restart ros-monitor-backend
```

### ROS2 QoS 不匹配
Livox ROS2 驱动默认使用 BEST_EFFORT 可靠性。如果遇到 IMU/LiDAR 无数据，检查 `robot_agent_ros2.py` 中 `_sensor_qos` 的 `reliability` 设置。

## 📚 文档

- [API 文档](http://43.136.76.169/docs) — FastAPI Swagger UI
- 配置文件: `ros_monitor_backend/config/`
  - `camera_topics.yaml` — 相机话题配置
  - `data_collection.yaml` — 数据采集脚本

## 🤝 贡献

1. Fork 项目
2. 创建分支 (`git checkout -b feature/xxx`)
3. 提交更改（遵循 Conventional Commits）
4. 创建 Pull Request

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)
