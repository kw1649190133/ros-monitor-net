# SLAM 可视化模块开发文档

## 概述

本文档记录了 ROS Monitor 系统中 SLAM 可视化模块的开发过程，包括后端订阅器、前端3D可视化组件的实现，以及问题排查记录。

## 功能需求

实现 SLAM 可视化监控模块，包含：
- `/cloud_registered` - 当前帧配准点云 (sensor_msgs/PointCloud2)
- `/aft_mapped_to_init` - 里程计位姿 (nav_msgs/Odometry)  
- `/path` - 运动轨迹 (nav_msgs/Path)
- 坐标轴和网格显示
- 点云累积显示 (Decay Time 参数可配置)
- 当前帧红色显示，历史地图使用真实RGB颜色

## 技术架构

### 后端 (Python/FastAPI)

#### 新增订阅器

| 文件 | 话题 | 消息类型 | 功能 |
|------|------|----------|------|
| `path_subscriber.py` | `/path` | nav_msgs/Path | 轨迹可视化 |
| `odometry_subscriber.py` | `/aft_mapped_to_init` | nav_msgs/Odometry | 当前位姿 |
| `registered_cloud_subscriber.py` | `/cloud_registered` | sensor_msgs/PointCloud2 | 点云地图 |

#### RGB颜色提取

`/cloud_registered` 话题的 PointCloud2 消息包含 RGB 颜色信息：

```python
# 消息字段结构
fields: [
  {name: 'x', offset: 0, datatype: 7 (FLOAT32)},
  {name: 'y', offset: 4, datatype: 7},
  {name: 'z', offset: 8, datatype: 7},
  {name: 'rgb', offset: 16, datatype: 7}  # packed float
]
```

RGB 解码方法（ROS 使用 BGR 顺序存储）：

```python
import struct

# rgb 是 packed float，需要转换为 int32 再提取各通道
rgb_int = struct.unpack('I', struct.pack('f', rgb_float))[0]
b = (rgb_int >> 0) & 0xFF
g = (rgb_int >> 8) & 0xFF
r = (rgb_int >> 16) & 0xFF
```

### 前端 (React/TypeScript/Three.js)

#### 依赖包

```bash
npm install three @react-three/fiber @react-three/drei @types/three
```

#### 核心组件

| 组件 | 功能 |
|------|------|
| `SLAMMonitor.tsx` | 主监控页面，包含统计信息和3D查看器 |
| `SLAMViewer3D.tsx` | Three.js 3D 可视化组件 |

#### 坐标系配置

采用 ROS 标准右手坐标系：**Z轴朝上，X前，Y左**

```typescript
// Canvas 相机配置
<Canvas camera={{ 
  position: [-5, -5, 5],  // 从后上方观察
  up: [0, 0, 1],          // Z轴朝上
  fov: 60 
}}>

// Grid 网格旋转到 XY 平面
<Grid rotation={[-Math.PI / 2, 0, 0]} />
```

#### 点云显示策略

| 组件 | 显示内容 | 颜色 | 点大小 |
|------|----------|------|--------|
| `CurrentFrameCloud` | 当前帧点云 | 固定红色 | 0.03 |
| `HistoryMapCloud` | 历史累积点云 | 真实RGB颜色 | 0.02 |

#### 状态管理 (Zustand)

```typescript
// useSensorStore.ts 中的 SLAM 状态
slam: {
  path: PathData | null;
  odometry: OdometryData | null;
  registeredCloud: RegisteredCloudData | null;
  pathHistory: PathData[];
  cloudHistory: RegisteredCloudData[];  // 累积点云历史
  decayTime: number;                     // 衰减时间(秒)，默认1000
  status: SensorStatus;
}
```

#### 类型定义

```typescript
// types/sensors.ts
export interface RegisteredCloudData {
  topic: string;
  timestamp: number;
  frame_id: string;
  sequence: number;
  total_points: number;
  sampled_points: number;
  points: number[][];      // [[x,y,z], ...]
  colors?: number[][];     // [[r,g,b], ...] 0-255
  has_rgb?: boolean;
  fields: string[];
}
```

## 问题排查记录

### 问题：历史地图显示为灰色而非真实RGB颜色

**现象**：当前帧红色正常，但历史地图全部显示为灰色。

**排查过程**：

1. **验证后端RGB提取**
```bash
# 检查 PointCloud2 消息字段
rostopic echo /cloud_registered --noarr -n 1
# 结果: fields: length: 4, 包含 x, y, z, rgb
```

2. **验证RGB解码正确性**
```python
# 测试脚本输出
Point 0: xyz=(6.97, 0.29, -1.15), RGB=(89, 112, 105)  # ✓ 正确
Point 1: xyz=(6.96, 0.37, -1.16), RGB=(71, 103, 105)  # ✓ 正确
```

3. **定位问题**

问题出在 `websocket.ts` 的 `handleRegisteredCloudData` 方法：

```typescript
// ❌ 错误：缺少 colors 和 has_rgb 字段
private handleRegisteredCloudData(data: any): void {
  sensorStore.updateRegisteredCloudData({
    topic: data.topic,
    timestamp: data.timestamp,
    // ... 
    points: data.points,
    fields: data.fields
    // 缺少: colors: data.colors,
    // 缺少: has_rgb: data.has_rgb,
  });
}
```

**修复方案**：

```typescript
// ✓ 正确：添加 colors 和 has_rgb
private handleRegisteredCloudData(data: any): void {
  sensorStore.updateRegisteredCloudData({
    topic: data.topic,
    timestamp: data.timestamp,
    frame_id: data.frame_id,
    sequence: data.sequence,
    total_points: data.total_points,
    sampled_points: data.sampled_points,
    points: data.points,
    colors: data.colors,      // ✓ 添加
    has_rgb: data.has_rgb,    // ✓ 添加
    fields: data.fields
  });
}
```

## 文件清单

### 后端新增/修改文件

```
ros_monitor_backend/src/
├── main.py                                    # 添加 SLAM 数据广播
└── ros_bridge/
    ├── node_manager.py                        # 添加 SLAM 订阅器管理
    └── subscribers/
        ├── path_subscriber.py                 # 新增
        ├── odometry_subscriber.py             # 新增
        └── registered_cloud_subscriber.py     # 新增
```

### 前端新增/修改文件

```
ros_monitor_frontend/src/
├── types/sensors.ts                           # 添加 SLAM 类型定义
├── stores/useSensorStore.ts                   # 添加 SLAM 状态管理
├── services/websocket.ts                      # 添加 SLAM 消息处理
└── components/
    ├── Layout/
    │   ├── MainLayout.tsx                     # 添加 SLAM 路由
    │   └── Sidebar.tsx                        # 添加 SLAM 菜单项
    └── SLAM/
        ├── SLAMMonitor.tsx                    # 新增
        └── SLAMViewer3D.tsx                   # 新增
```

## 待办事项

- [ ] 修复 WebSocket 中 colors/has_rgb 字段传递问题
- [ ] 添加点云降采样参数可配置
- [ ] 优化大量点云渲染性能
- [ ] 添加视角重置按钮

