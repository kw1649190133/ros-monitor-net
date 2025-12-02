# ROS监控系统 (ROS Monitor System)

一个基于FastAPI和React的多传感器融合监控平台，专为IKing Handbot机器人项目设计，支持激光雷达、IMU、相机等传感器数据的实时监控和可视化。

## 🚀 项目特性

- **实时数据监控**: 支持ROS话题的实时订阅和数据流
- **多传感器支持**: 激光雷达、IMU、相机、GNSS/RTK等多种传感器
- **WebSocket通信**: 实时数据推送和双向通信
- **现代化前端**: 基于React + TypeScript + Ant Design
- **RESTful API**: 完整的后端API接口
- **系统监控**: 算法启停控制、录制控制、系统状态监控
- **配置化管理**: 灵活的YAML配置文件支持
- **快速部署**: 一键部署脚本和环境检查工具

## 🏗️ 系统架构

```
ROS Monitor System
├── ros_monitor_backend/     # FastAPI后端服务
│   ├── src/                # 核心源代码
│   ├── config/             # 配置文件(YAML)
│   ├── tests/              # 测试文件
│   └── requirements.txt    # Python依赖
├── ros_monitor_frontend/   # React前端应用
│   ├── src/                # 前端源代码
│   └── package.json        # Node.js依赖
├── script/                 # 数据采集脚本
├── Documents/              # 项目文档
├── environment.yml         # 环境规格文件
├── .env.example            # 环境变量模板
├── deploy.sh               # 一键部署脚本
├── check_environment.sh    # 环境检查脚本
└── export_environment.sh   # 环境快照导出
```

## 🛠️ 技术栈

### 后端
- **FastAPI**: 现代Python Web框架
- **WebSocket**: 实时双向通信
- **ROS集成**: rospy, cv_bridge, gnss_comm等
- **数据处理**: OpenCV, NumPy
- **配置管理**: PyYAML配置文件支持

### 前端
- **React 19**: 最新版本React框架
- **TypeScript**: 类型安全的JavaScript
- **Ant Design**: 企业级UI组件库
- **ECharts**: 数据可视化图表
- **Three.js**: 3D可视化 (react-three-fiber + drei)
- **Zustand**: 轻量级状态管理

## 📦 快速开始

### 环境要求
- Python 3.8+
- Node.js 18+
- ROS Noetic/Melodic
- Ubuntu 20.04+

### 方法1: 自动化部署（推荐）

```bash
# 1. 克隆项目
git clone <repository-url>
cd ROS_monitor

# 2. 检查环境
./check_environment.sh

# 3. 一键部署
./deploy.sh

# 4. 配置环境变量
cp .env.example .env
vim .env  # 修改配置

# 5. 启动服务
cd ros_monitor_backend && ./start_backend.sh
cd ros_monitor_frontend && ./start_frontend.sh
```

### 方法2: 手动部署

#### 2.1 启动后端服务
```bash
cd ros_monitor_backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
./start_backend.sh
```

#### 2.2 启动前端应用
```bash
cd ros_monitor_frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build
```

## 🔧 配置说明

### 环境变量配置
复制 `.env.example` 为 `.env` 并修改配置：
```bash
cp .env.example .env
vim .env
```

主要配置项：
- `ROS_MASTER_URI`: ROS Master地址
- `ROS_IP`: 本机IP地址
- `ROS_MONITOR_PORT`: 后端服务端口（默认8001）
- `VITE_API_HOST`: 前端访问后端的地址

### 后端配置
- 默认端口: 8001 (可通过环境变量或 --port 参数修改)
- WebSocket端点: `/ws/{client_id}`
- API文档: `http://localhost:8001/docs`
- 配置文件目录: `ros_monitor_backend/config/`
  - `camera_topics.yaml`: 相机话题配置
  - `data_collection.yaml`: 数据采集脚本配置

### 前端配置
- 开发端口: 5173
- 构建输出: `dist/`目录
- 代理配置: `vite.config.ts`

## 📊 功能模块

### 传感器监控
- **激光雷达**: 点云数据实时显示
- **IMU**: 姿态和运动数据监控
- **相机**: 多相机图像流监控（支持压缩图像话题）
- **GNSS/RTK**: GPS定位和RTK状态监控

### SLAM可视化
- **轨迹显示**: 实时机器人运动轨迹 (`/path`)
- **位姿监控**: 当前里程计位姿 (`/aft_mapped_to_init`)
- **点云地图**: 配准点云累积显示 (`/cloud_registered`)
- **坐标系**: Z轴朝上的ROS标准右手坐标系
- **Decay Time**: 可配置的点云衰减时间 (1-10000秒)
- **RGB颜色**: 历史地图使用真实RGB颜色，当前帧红色高亮

### 系统控制
- **数据采集控制**: 启动/停止数据采集（通过配置化脚本）
- **录制控制**: 数据录制管理
- **状态监控**: 系统运行状态和连接状态

### 数据可视化
- **实时图表**: ECharts图表展示
- **3D可视化**: Three.js点云和轨迹显示
- **历史数据**: 数据回放和分析

## 🧪 测试

### 后端测试
```bash
cd ros_monitor_backend
python -m pytest tests/
```

### 前端测试
```bash
cd ros_monitor_frontend
npm run lint
npm test
```

### 端到端测试
```bash
python test_end_to_end.py
```

## 📚 文档

- [环境规格文件](environment.yml) - 依赖版本说明
- [部署指南](Documents/) - 快速部署文档
- [相机配置说明](Documents/CAMERA_CONFIGURATION.md)
- [端口配置说明](Documents/PORT_CONFIGURATION.md)
- [GNSS数据结构](Documents/GNSS消息数据结构分析文档.md)
- [SLAM可视化模块](docs/SLAM_Visualization_Module.md) - SLAM开发文档
- [API文档](http://localhost:8001/docs) - FastAPI自动生成

## 🔍 环境管理

### 导出当前环境
```bash
./export_environment.sh
cat environment_snapshot.txt
```

### 检查环境状态
```bash
./check_environment.sh
```

### 环境规格说明
详见 `environment.yml` 文件，包含：
- 系统要求
- 运行时版本
- Python依赖
- Node.js依赖
- ROS包依赖

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🙏 致谢

- IKing Handbot项目团队
- ROS社区
- FastAPI和React开源社区

## 📞 联系方式

- 项目维护者: YCS
- 项目地址: [GitHub Repository]
- 问题反馈: [Issues]

## 🚧 待开发功能 (TODO)

### 可视化增强
- [x] **位姿轨迹可视化**: 支持机器人位姿轨迹的实时显示
- [x] **点云地图累积**: 支持Decay Time配置的点云累积显示
- [ ] **点云降采样优化**: 优化大规模点云数据的显示性能

### 时间同步模块
- [ ] **PTP/NTP时间同步**: 支持高精度时间同步协议启动和配置
- [ ] **同步信息统计**: 实时显示时间同步状态和统计信息
- [ ] **时间同步延时监控**: 监控和可视化时间同步延迟指标

### 数据管理
- [ ] **录制数据命名**: 支持为录制数据自定义名称并保存，便于后续检索和管理

## 🚨 常见问题

### 端口被占用
后端服务会自动检测并使用可用端口（8001-8100），如需指定端口：
```bash
export ROS_MONITOR_PORT=8002
./start_backend.sh
```

### GNSS功能不可用
GNSS功能需要 `gnss_comm` 包，必须从源码编译：
```bash
cd /path/to/ublox_ws
source devel/setup.bash
```

### 相机话题配置
编辑 `ros_monitor_backend/config/camera_topics.yaml` 配置相机话题。

### 数据采集脚本路径
编辑 `ros_monitor_backend/config/data_collection.yaml` 配置脚本路径。

---

**注意**: 
- 本项目需要ROS环境支持，请确保已正确安装和配置ROS系统
- 默认后端端口已从 8000 改为 8001
- 首次部署建议使用 `./deploy.sh` 自动化脚本
