#!/usr/bin/env python3
"""
多机器人虚拟连接测试程序
模拟多种类型机器人同时连接到后端，验证前端多机器人切换功能。

机器人类型:
  - 无人机 (Drone)      — GNSS + IMU + 相机 + 飞行轨迹
  - 地面机器人 (Rover)  — LiDAR + IMU + GNSS + SLAM + 星形轨迹
  - 水下ROV (Underwater) — 深度计 + IMU + 声纳模拟 + 平面轨迹
  - 物流小车 (AGV)      — 里程计 + 电池 + 相机 + 直线轨迹

用法:
    pip install websocket-client numpy
    python mock_multi_robot_test.py

    可选参数:
    --server HOST     服务器地址（默认 localhost）
    --port PORT       服务器端口（默认 8001）
    --count N         启动机器人数量（默认 4）
    --no-camera       禁用相机模拟（降低 CPU 占用）
"""

import sys
import time
import json
import math
import random
import socket
import signal
import argparse
import threading
import logging
from typing import Optional, Dict, List, Any

# ---- 彩色日志 ----
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[90m', 'INFO': '\033[37m', 'WARNING': '\033[93m',
        'ERROR': '\033[91m', 'CRITICAL': '\033[95m',
    }
    RESET = '\033[0m'
    ROBOT_COLORS = [
        '\033[96m', '\033[92m', '\033[94m', '\033[95m',
        '\033[93m', '\033[91m', '\033[90m', '\033[97m',
    ]

    def format(self, record):
        color = self.ROBOT_COLORS[hash(record.name) % len(self.ROBOT_COLORS)]
        lvl_color = self.COLORS.get(record.levelname, '')
        record.msg = f"{color}[{record.name}]{self.RESET} {lvl_color}{record.msg}{self.RESET}"
        return super().format(record)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S'))
logging.getLogger().handlers.clear()
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

try:
    import websocket
except ImportError:
    print("请安装: pip install websocket-client")
    sys.exit(1)

try:
    import numpy as np
    HAS_CV2 = True
    import cv2
except ImportError:
    HAS_CV2 = False

# ============================================================
# 机器人配置档案
# ============================================================

ROBOT_PROFILES = {
    'drone': {
        'name': '无人机',
        'emoji': '🛸',
        'type': 'aerial',
        'ros_version': 'ROS2 Humble',
        'capabilities': ['gnss', 'imu', 'camera', 'battery'],
        'base_lat': 39.0790108,
        'base_lon': 117.7151327,
        'base_alt': 50.0,   # 高空
        'push_interval': 0.5,  # 降低频率防止数据洪流
    },
    'rover': {
        'name': '地面车',
        'emoji': '🚜',
        'type': 'ground',
        'ros_version': 'ROS1 Noetic',
        'capabilities': ['lidar', 'imu', 'gnss', 'slam', 'camera', 'battery'],
        'base_lat': 39.0780108,
        'base_lon': 117.7141327,
        'base_alt': -2.0,
        'push_interval': 0.5,  # 降低频率防止数据洪流
    },
    'rov': {
        'name': '水下ROV',
        'emoji': '🌊',
        'type': 'underwater',
        'ros_version': 'ROS2 Humble',
        'capabilities': ['depth', 'imu', 'sonar', 'battery'],
        'base_lat': 22.543099,  # 深圳海域
        'base_lon': 114.057868,
        'base_alt': -15.0,  # 水下15米
        'push_interval': 0.5,    },
    'agv': {
        'name': '物流小车',
        'emoji': '🚚',
        'type': 'ground',
        'ros_version': 'ROS2 Foxy',
        'capabilities': ['odometry', 'camera', 'battery', 'ultrasonic'],
        'base_lat': 39.0800108,
        'base_lon': 117.7161327,
        'base_alt': -2.0,
        'push_interval': 0.5,
    },
}

# ============================================================
# 传感器模拟器（每个机器人独立实例）
# ============================================================

class SensorSimulator:
    """独立传感器模拟器，每个机器人拥有不同的运动模式。"""

    MOTION_PATTERNS = {
        'aerial': 'circle',    # 无人机绕圈飞
        'ground': 'star',      # 地面车走星形
        'underwater': 'zigzag', # ROV 走之字形
    }

    def __init__(self, profile: dict, robot_index: int):
        self.profile = profile
        self.robot_index = robot_index
        self._start_time = time.time()
        self._seq = {'lidar': 0, 'imu': 0, 'gnss': 0, 'camera': 0, 'depth': 0, 'sonar': 0, 'battery': 0}

        # 基础位置（每台机器人微调 GPS 起点，避免重叠）
        lat_offset = random.uniform(-0.001, 0.001)
        lon_offset = random.uniform(-0.001, 0.001)
        self.base_lat = profile['base_lat'] + lat_offset
        self.base_lon = profile['base_lon'] + lon_offset
        self.base_alt = profile['base_alt']

        self.capabilities = set(profile.get('capabilities', []))
        self.motion = self.MOTION_PATTERNS.get(profile['type'], 'circle')

        # 预生成 LiDAR 点云（仅地面车）
        if 'lidar' in self.capabilities:
            self._lidar_pts = self._make_room_scan(n_points=500)

        # 电池初始值
        self._battery = random.uniform(70, 100)

    def elapsed(self) -> float:
        return time.time() - self._start_time

    # ---- 运动位置计算 ----

    def _get_motion_offset(self) -> tuple:
        """根据运动模式计算相对起点的偏移 (lat_delta, lon_delta, alt_delta)。"""
        t = self.elapsed()
        scale = 0.00003  # ~3m 在地球表面的度数

        if self.motion == 'circle':
            radius = 2.0 + self.robot_index * 0.5
            ang = t * 0.3
            dx = radius * math.cos(ang) * scale
            dy = radius * math.sin(ang) * scale
            dz = math.sin(t * 0.2) * 3.0
            return dx, dy, dz

        elif self.motion == 'star':
            r = 1.5 + self.robot_index * 0.3
            ang = t * 0.25
            k = 0 if t % 8 < 4 else 1
            pts = [(r, 0), (r*0.31, r*0.95), (-r*0.81, r*0.59),
                   (-r*0.81, -r*0.59), (r*0.31, -r*0.95)]
            idx = int(ang / (2*math.pi/5)) % 5
            frac = (ang % (2*math.pi/5)) / (2*math.pi/5)
            p0 = pts[idx]
            p1 = pts[(idx+1)%5]
            px = p0[0] + (p1[0]-p0[0])*frac
            py = p0[1] + (p1[1]-p0[1])*frac
            return px*scale, py*scale, math.sin(t*0.3)*0.5

        elif self.motion == 'zigzag':
            segment = int(t / 5)
            seg_t = t % 5
            direction = 1 if segment % 2 == 0 else -1
            dx = seg_t * 1.5 * scale
            dy = direction * 2.0 * scale
            dz = math.sin(t * 0.4) * 1.0
            return dx, dy, dz

        return 0, 0, 0

    def _get_current_position(self) -> dict:
        dx, dy, dz = self._get_motion_offset()
        return {
            'latitude': round(self.base_lat + dx, 8),
            'longitude': round(self.base_lon + dy, 8),
            'altitude': round(self.base_alt + dz, 3),
        }

    # ---- 点云生成 ----

    @staticmethod
    def _make_room_scan(n_points=500):
        """模拟室内扫描点云。"""
        pts = []
        walls = [
            (0, 4, 0, 3), (4, 0, 0, 3),
            (0, -4, 0, 3), (-4, 0, 0, 3),
        ]
        for wx, wy, z0, z1 in walls:
            for _ in range(n_points // 4):
                if wx == 0:
                    px = random.uniform(-4, 4)
                    py = wy + random.uniform(-0.15, 0.15)
                else:
                    px = wx + random.uniform(-0.15, 0.15)
                    py = random.uniform(-4, 4)
                pz = random.uniform(z0, z1)
                pts.append([round(px, 3), round(py, 3), round(pz, 3)])
        # 地面
        for _ in range(n_points // 4):
            pts.append([round(random.uniform(-4, 4), 3),
                        round(random.uniform(-4, 4), 3),
                        0.0])
        return pts

    # ---- 传感器数据生成 ----

    def generate_lidar(self) -> dict:
        self._seq['lidar'] += 1
        t = self.elapsed()
        angle = t * 0.5
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        rotated = []
        for x, y, z in self._lidar_pts:
            rx = x * cos_a - y * sin_a
            ry = x * sin_a + y * cos_a
            rotated.append([round(rx + random.uniform(-0.02,0.02), 4),
                            round(ry + random.uniform(-0.02,0.02), 4),
                            round(z + random.uniform(-0.01,0.01), 4)])
        return {
            'timestamp': t, 'frame_id': 'lidar_frame',
            'point_count': len(rotated),
            'fields': [{'name': 'x', 'offset': 0, 'datatype': 7, 'count': 1},
                       {'name': 'y', 'offset': 4, 'datatype': 7, 'count': 1},
                       {'name': 'z', 'offset': 8, 'datatype': 7, 'count': 1}],
            'data': rotated, 'compression': 'none',
        }

    def generate_imu(self) -> dict:
        self._seq['imu'] += 1
        t = self.elapsed()
        roll  = math.sin(t * 0.5 + self.robot_index) * 0.08
        pitch = math.cos(t * 0.7 + self.robot_index) * 0.06
        yaw   = t * 0.15
        cy, sy = math.cos(yaw/2), math.sin(yaw/2)
        cp, sp = math.cos(pitch/2), math.sin(pitch/2)
        cr, sr = math.cos(roll/2), math.sin(roll/2)
        return {
            'timestamp': t,
            'orientation': {
                'x': round(sr*cp*cy - cr*sp*sy, 6),
                'y': round(cr*sp*cy + sr*cp*sy, 6),
                'z': round(cr*cp*sy - sr*sp*cy, 6),
                'w': round(cr*cp*cy + sr*sp*sy, 6),
            },
            'angular_velocity': {
                'x': round(math.cos(t*0.4)*0.15, 6),
                'y': round(math.sin(t*0.6)*0.12, 6),
                'z': round(random.uniform(-0.04, 0.04), 6),
            },
            'linear_acceleration': {
                'x': round(random.uniform(-0.2, 0.2), 6),
                'y': round(random.uniform(-0.15, 0.15), 6),
                'z': round(9.8 + random.uniform(-0.08, 0.08), 6),
            },
        }

    def generate_gnss(self) -> dict:
        self._seq['gnss'] += 1
        t = self.elapsed()
        pos = self._get_current_position()
        statuses = ['RTK_FIXED', 'RTK_FIXED', 'RTK_FIXED', 'RTK_FLOAT']
        rtk = random.choice(statuses)
        num_sv = random.randint(14, 30) if self.profile['type'] == 'aerial' else random.randint(8, 20)
        return {
            'rtk_status': rtk,
            'quality': {
                'fix_type': 3, 'valid_fix': True,
                'diff_soln': True,
                'carr_soln': 2 if rtk == 'RTK_FIXED' else 1,
                'num_sv': num_sv,
            },
            'position': {
                'latitude': round(pos['latitude'] + random.uniform(-1e-7, 1e-7), 8),
                'longitude': round(pos['longitude'] + random.uniform(-1e-7, 1e-7), 8),
                'altitude': round(pos['altitude'] + random.uniform(-0.03, 0.03), 3),
                'height_msl': round(pos['altitude'] + 7.0, 3),
            },
            'accuracy': {
                'h_acc': round(random.uniform(0.006, 0.018), 4),
                'v_acc': round(random.uniform(0.01, 0.025), 4),
                'p_dop': round(random.uniform(0.5, 1.3), 2),
            },
            'velocity': {
                'vel_n': round(random.uniform(-0.5, 0.5), 3),
                'vel_e': round(random.uniform(-0.5, 0.5), 3),
                'vel_d': round(random.uniform(-0.1, 0.1), 3),
                'vel_acc': round(random.uniform(0.08, 0.15), 3),
            },
            'time': {'week': 2393, 'tow': t},
            'timestamp': t, 'sequence': self._seq['gnss'],
        }

    def generate_camera(self, camera_id: str) -> Optional[dict]:
        if not HAS_CV2:
            return None
        self._seq['camera'] += 1
        t = self.elapsed()
        h, w = 360, 480
        img = np.zeros((h, w, 3), dtype=np.uint8)

        # 根据机器人类型不同背景色
        bg_color = {
            'aerial': (100, 80, 40),   # 暖黄色（天空）
            'ground': (40, 60, 40),     # 暗绿色（地面）
            'underwater': (30, 30, 100), # 蓝色（水下）
        }.get(self.profile['type'], (60, 60, 60))

        for i in range(h):
            shade = int(i * 0.2)
            cv2.line(img, (0, i), (w, i),
                     (min(255, bg_color[0]+shade), min(255, bg_color[1]+shade), min(255, bg_color[2]+shade)), 1)

        # 十字线 + 信息
        cv2.line(img, (w//2, 0), (w//2, h), (0, 255, 0), 1)
        cv2.line(img, (0, h//2), (w, h//2), (0, 255, 0), 1)
        fonts = [
            f'{self.profile["emoji"]} {self.profile["name"]} [{camera_id}]',
            f'Frame: {self._seq["camera"]}  |  Time: {t:.1f}s',
            f'{self.profile["type"].upper()}  {self.profile["ros_version"]}',
        ]
        y = 25
        for text in fonts:
            cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            y += 25

        # 移动目标点
        cx = int(w/2 + math.sin(t*2 + self.robot_index)*120)
        cy = int(h/2 + math.cos(t*3 + self.robot_index)*80)
        cv2.circle(img, (cx, cy), 12, (0, 0, 255), -1)

        _, jpeg_data = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        import base64
        return {
            'camera_id': camera_id, 'topic': f'/mock/{camera_id}/image/compressed',
            'timestamp': t, 'encoding': 'jpeg',
            'width': w, 'height': h,
            'data': base64.b64encode(jpeg_data).decode('utf-8'),
            'compressed': True, 'sequence': self._seq['camera'],
        }

    def generate_slam_path(self) -> dict:
        t = self.elapsed()
        poses = []
        for i in range(50):
            r = i * 0.12
            angle = t * 0.2 + i * 0.07 + self.robot_index * 0.5
            poses.append({
                'position': {'x': round(r*math.cos(angle), 3),
                             'y': round(r*math.sin(angle), 3),
                             'z': round(i*0.008, 3)},
                'orientation': {'x': 0.0, 'y': 0.0,
                                'z': round(math.sin(angle/2), 4),
                                'w': round(math.cos(angle/2), 4)},
            })
        return {
            'topic': '/path', 'timestamp': t, 'frame_id': 'map',
            'sequence': 0, 'total_poses': len(poses),
            'sampled_poses': len(poses), 'poses': poses,
        }

    def generate_slam_odometry(self) -> dict:
        t = self.elapsed()
        r = 8.0 + self.robot_index
        ang = t * 0.2
        return {
            'topic': '/aft_mapped_to_init', 'timestamp': t,
            'frame_id': 'map', 'child_frame_id': 'base_link', 'sequence': 0,
            'pose': {
                'position': {'x': round(r*math.cos(ang), 3),
                             'y': round(r*math.sin(ang), 3), 'z': 0.0},
                'orientation': {'x': 0.0, 'y': 0.0,
                                'z': round(math.sin((ang+math.pi/2)/2), 4),
                                'w': round(math.cos((ang+math.pi/2)/2), 4)},
            },
            'twist': {
                'linear': {'x': 0.0, 'y': round(r*0.2, 3), 'z': 0.0},
                'angular': {'x': 0.0, 'y': 0.0, 'z': 0.2},
            },
        }

    def generate_cloud_map(self) -> dict:
        t = self.elapsed()
        pts, colors = [], []
        walls = [
            (0, 5, -2, 2, (255, 100, 100)),
            (5, 0, -2, 2, (100, 255, 100)),
            (0, -5, -2, 2, (100, 100, 255)),
            (-5, 0, -2, 2, (255, 255, 100)),
            (0, 0, 2, 1, (200, 200, 200)),
            (0, 0, -2, -1, (100, 100, 100)),
        ]
        for wx, wy, z0, z1, color in walls:
            for _ in range(60):
                if wx == 0:
                    px = random.uniform(-5, 5)
                    py = wy + random.uniform(-0.1, 0.1)
                elif wy == 0:
                    px = wx + random.uniform(-0.1, 0.1)
                    py = random.uniform(-5, 5)
                else:
                    px = wx + random.uniform(-5, 5)
                    py = wy + random.uniform(-5, 5)
                pz = z0 if z0 == z1 else random.uniform(min(z0,z1), max(z0,z1))
                pts.append([round(px, 3), round(py, 3), round(pz, 3)])
                colors.append(list(color))

        ang = t * 0.4
        for _ in range(80):
            r = random.uniform(1, 6)
            a = ang + random.uniform(-0.5, 0.5)
            pts.append([round(r*math.cos(a),3), round(r*math.sin(a),3),
                        round(random.uniform(-1,2),3)])
            colors.append([255, 50, 50])
        return {
            'topic': '/cloud_registered', 'timestamp': t,
            'frame_id': 'map', 'sequence': 0,
            'total_points': len(pts), 'sampled_points': len(pts),
            'points': pts, 'colors': colors, 'has_rgb': True,
            'fields': ['x', 'y', 'z', 'rgb'],
        }

    def generate_depth(self) -> dict:
        """水下深度计模拟。"""
        self._seq['depth'] += 1
        t = self.elapsed()
        base_depth = abs(self.base_alt)
        depth = base_depth + math.sin(t * 0.3) * 2.0 + random.uniform(-0.1, 0.1)
        return {
            'timestamp': t, 'depth': round(depth, 2),
            'pressure': round(depth * 0.101 + 1.013, 3),  # MPa
            'temperature': round(25.0 - depth * 0.5 + random.uniform(-0.3, 0.3), 1),
            'sequence': self._seq['depth'],
        }

    def generate_sonar(self) -> dict:
        """声纳模拟（模拟水下障碍物扫描）。"""
        self._seq['sonar'] += 1
        t = self.elapsed()
        ranges = []
        for i in range(36):  # 360度/10度
            ang = i * 10 * math.pi / 180
            base_range = 5.0 + 2.0 * math.sin(ang * 2 + t)
            ranges.append(round(base_range + random.uniform(-0.5, 0.5), 2))
        return {
            'timestamp': t, 'ranges': ranges,
            'angle_min': -math.pi, 'angle_max': math.pi,
            'angle_increment': math.pi / 18,
            'range_min': 0.5, 'range_max': 15.0,
            'sequence': self._seq['sonar'],
        }

    def generate_odometry(self) -> dict:
        """AGV 里程计。"""
        t = self.elapsed()
        dist = t * 0.8  # 0.8 m/s
        x = dist * math.cos(self.robot_index * 0.7)
        y = dist * math.sin(self.robot_index * 0.7)
        return {
            'timestamp': t, 'frame_id': 'odom',
            'child_frame_id': 'base_link', 'sequence': 0,
            'pose': {
                'position': {'x': round(x, 3), 'y': round(y, 3), 'z': 0.0},
                'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0},
            },
            'velocity': {
                'linear': {'x': 0.8, 'y': 0.0, 'z': 0.0},
                'angular': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            },
        }

    def generate_ultrasonic(self) -> dict:
        """AGV 超声波避障传感器。"""
        sensors = ['front', 'rear', 'left', 'right']
        return {
            'timestamp': self.elapsed(),
            'readings': {s: round(random.uniform(0.3, 5.0), 2) for s in sensors},
            'warning': any(v < 0.5 for v in [round(random.uniform(0.3, 5.0), 2)]),
        }

    def generate_battery(self) -> dict:
        """电池状态。"""
        self._seq['battery'] += 1
        self._battery -= random.uniform(0.001, 0.005)
        if self._battery < 10:
            self._battery = 100  # 模拟换电
        t = self.elapsed()
        voltage = 11.1 + (self._battery / 100) * 1.5  # 3S LiPo
        return {
            'timestamp': t,
            'percentage': round(self._battery, 1),
            'voltage': round(voltage, 2),
            'current': round(random.uniform(-5, 20), 2),
            'temperature': round(30 + random.uniform(-5, 15), 1),
            'cells': [
                round(voltage/3 + random.uniform(-0.02, 0.02), 2),
                round(voltage/3 + random.uniform(-0.02, 0.02), 2),
                round(voltage/3 + random.uniform(-0.02, 0.02), 2),
            ],
            'status': 'discharging',
            'sequence': self._seq['battery'],
        }


# ============================================================
# 模拟机器人
# ============================================================

class MockRobot:
    """单台模拟机器人。"""

    def __init__(self, robot_id: str, profile: dict, server_url: str,
                 enable_camera: bool = True):
        self.robot_id = robot_id
        self.profile = profile
        self.enable_camera = enable_camera and HAS_CV2

        # WebSocket URL 构造
        self.ws_url = f"{server_url}/ws/robot/{robot_id}"

        self.logger = logging.getLogger(robot_id)
        self.ws: Optional[websocket.WebSocketApp] = None
        self.sim = SensorSimulator(profile, hash(robot_id) % 100)
        self._running = False
        self._connected = threading.Event()
        self._push_interval = profile.get('push_interval', 0.1)
        self._registered = False
        self._stats = {'messages_sent': 0, 'bytes_sent': 0, 'last_seen': 0}

    # ---- WebSocket 回调 ----

    def _on_open(self, ws):
        self.logger.info(f"已连接 → {self.ws_url}")
        self._connected.set()
        # 发送注册消息
        self._send({
            'type': 'robot_register',
            'robot_id': self.robot_id,
            'hostname': f"{self.profile['emoji']}{self.profile['name']}-{self.robot_id}",
            'ip': self._get_local_ip(),
            'ros_version': self.profile.get('ros_version', 'unknown'),
            'robot_type': self.profile['type'],
            'capabilities': list(self.profile.get('capabilities', [])),
            'timestamp': time.time(),
        })

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')

            if msg_type == 'robot_registered':
                self.logger.info(f"✅ 服务器确认注册: {data.get('message', '')}")
                self._registered = True

            elif msg_type == 'robot_command':
                self.logger.info(f"📩 收到云端指令: {data.get('command', {})}")
                # 简单回执
                self._send({
                    'type': 'command_ack',
                    'robot_id': self.robot_id,
                    'command': data.get('command', {}),
                    'status': 'received',
                })

            elif msg_type == 'ping':
                self._send({'type': 'pong', 'timestamp': time.time()})

        except Exception:
            pass

    def _on_error(self, ws, error):
        self.logger.error(f"WebSocket 错误: {error}")

    def _on_close(self, ws, code, msg):
        self.logger.warning(f"断开连接 (code={code})")
        self._connected.clear()
        self._registered = False
        if self._running:
            time.sleep(3)
            self._connect()

    # ---- 连接管理 ----

    def _connect(self):
        self.logger.info(f"正在连接: {self.ws_url}")
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        t = threading.Thread(target=self.ws.run_forever,
                             kwargs={'ping_interval': 15, 'ping_timeout': 5})
        t.daemon = True
        t.start()

    def _send(self, data: dict):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                raw = json.dumps(data)
                self.ws.send(raw)
                self._stats['messages_sent'] += 1
                self._stats['bytes_sent'] += len(raw)
                self._stats['last_seen'] = time.time()
        except Exception as e:
            self.logger.debug(f"发送失败: {e}")

    def _push_sensor(self, topic_name: str, data: dict, **extra):
        msg = {'type': 'sensor_data', 'topic_name': topic_name, 'data': data}
        msg.update(extra)
        self._send(msg)

    # ---- 主循环 ----

    def _push_loop(self):
        cap = self.sim.capabilities
        interval = self._push_interval
        self.logger.info(f"开始推送数据 (间隔={interval}s, 能力={list(cap)})")
        frame = 0

        while self._running:
            try:
                t0 = time.time()

                # LiDAR（地面车）
                if 'lidar' in cap and frame % 1 == 0:
                    self._push_sensor('/livox/lidar', self.sim.generate_lidar())

                # IMU（所有类型）
                if 'imu' in cap and frame % 1 == 0:
                    self._push_sensor('/livox/imu', self.sim.generate_imu())

                # GNSS（非水下）
                if 'gnss' in cap and frame % 10 == 0:
                    self._push_sensor('/ublox_driver/receiver_lla', self.sim.generate_gnss())

                # 相机（每 5 帧）
                if 'camera' in cap and self.enable_camera and frame % 5 == 0:
                    cam = self.sim.generate_camera('main_camera')
                    if cam:
                        self._push_sensor(cam['topic'], cam, camera_id='main_camera')

                # SLAM（地面车）
                if 'slam' in cap and frame % 2 == 0:
                    self._push_sensor('/path', self.sim.generate_slam_path())
                    self._push_sensor('/aft_mapped_to_init', self.sim.generate_slam_odometry())
                    self._push_sensor('/cloud_registered', self.sim.generate_cloud_map())

                # 深度计（水下ROV）
                if 'depth' in cap and frame % 5 == 0:
                    self._push_sensor('/depth_sensor', self.sim.generate_depth())

                # 声纳（水下ROV）
                if 'sonar' in cap and frame % 3 == 0:
                    self._push_sensor('/sonar', self.sim.generate_sonar())

                # 里程计（AGV）
                if 'odometry' in cap and frame % 1 == 0:
                    self._push_sensor('/odom', self.sim.generate_odometry())

                # 超声波（AGV）
                if 'ultrasonic' in cap and frame % 10 == 0:
                    self._push_sensor('/ultrasonic', self.sim.generate_ultrasonic())

                # 电池（所有机器人）
                if 'battery' in cap and frame % 50 == 0:
                    self._push_sensor('/battery', self.sim.generate_battery())

                frame += 1
                elapsed = time.time() - t0
                sleep_time = max(0.001, interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"推送异常: {e}")
                time.sleep(1)

    # ---- 公开方法 ----

    def start(self):
        self._running = True
        self._connect()
        # 等待连接建立
        if not self._connected.wait(timeout=10):
            self.logger.error("连接超时！")
            self._running = False
            return False
        # 等待注册确认
        time.sleep(1.0)
        # 启动推送线程
        t = threading.Thread(target=self._push_loop, daemon=True)
        t.start()
        return True

    def stop(self):
        self._running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.logger.info("已停止")

    def get_stats(self) -> dict:
        return {
            'robot_id': self.robot_id,
            'profile': f"{self.profile['emoji']} {self.profile['name']}",
            'type': self.profile['type'],
            'connected': self._connected.is_set(),
            'registered': self._registered,
            'messages_sent': self._stats['messages_sent'],
            'bytes_sent_kb': round(self._stats['bytes_sent'] / 1024, 1),
            'last_seen': round(time.time() - self._stats['last_seen'], 1) if self._stats['last_seen'] else -1,
        }

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return 'unknown'


# ============================================================
# 多机器人管理器
# ============================================================

class MultiRobotManager:
    """管理多台模拟机器人的生命周期。"""

    def __init__(self, server_url: str, enable_camera: bool = True):
        self.server_url = server_url
        self.enable_camera = enable_camera
        self.robots: Dict[str, MockRobot] = {}
        self._next_index = {'drone': 0, 'rover': 0, 'rov': 0, 'agv': 0}
        self.logger = logging.getLogger('Manager')

    def add_robot(self, robot_type: str) -> Optional[str]:
        """添加一台机器人。"""
        profile = ROBOT_PROFILES.get(robot_type)
        if not profile:
            self.logger.error(f"未知机器人类型: {robot_type}")
            return None

        idx = self._next_index[robot_type]
        self._next_index[robot_type] += 1
        robot_id = f"{robot_type}-{idx+1:02d}"

        bot = MockRobot(robot_id, profile, self.server_url, self.enable_camera)
        self.robots[robot_id] = bot

        self.logger.info(f"创建机器人: {profile['emoji']} {robot_id} ({profile['name']})")
        success = bot.start()

        if success:
            self.logger.info(f"✅ {robot_id} 启动成功")
            return robot_id
        else:
            self.logger.error(f"❌ {robot_id} 启动失败")
            self.robots.pop(robot_id, None)
            return None

    def remove_robot(self, robot_id: str) -> bool:
        if robot_id in self.robots:
            self.robots[robot_id].stop()
            del self.robots[robot_id]
            self.logger.info(f"已移除: {robot_id}")
            return True
        return False

    def stop_all(self):
        self.logger.info("正在停止所有机器人...")
        for bot in list(self.robots.values()):
            bot.stop()
        self.robots.clear()
        self.logger.info("全部已停止")

    def list_robots(self) -> List[dict]:
        return [bot.get_stats() for bot in self.robots.values()]

    def get_robot(self, robot_id: str) -> Optional[MockRobot]:
        return self.robots.get(robot_id)

    @property
    def count(self) -> int:
        return len(self.robots)


# ============================================================
# 状态显示
# ============================================================

def print_status(manager: MultiRobotManager):
    """打印在线机器人状态表。"""
    stats = manager.list_robots()
    if not stats:
        print("\n  (无在线机器人)")
        return

    print(f"\n{'='*70}")
    print(f"  在线机器人: {len(stats)} 台")
    print(f"{'-'*70}")
    print(f"  {'ID':<14} {'类型':<10} {'连接':<8} {'消息数':<8} {'流量(KB)':<10} {'延迟(s)'}")
    print(f"{'-'*70}")
    for s in stats:
        conn_status = '🟢' if s['connected'] else '🔴'
        print(f"  {s['robot_id']:<14} {s['profile']:<10} {conn_status:<8} "
              f"{s['messages_sent']:<8} {s['bytes_sent_kb']:<10} {s['last_seen']}")
    print(f"{'='*70}\n")


# ============================================================
# 交互控制台
# ============================================================

def print_help():
    print("""
┌─────────────────────────────────────────────────────────────┐
│                    多机器人测试控制台                          │
├─────────────────────────────────────────────────────────────┤
│  add drone     — 添加无人机                                  │
│  add rover     — 添加地面机器人                               │
│  add rov       — 添加水下ROV                                 │
│  add agv       — 添加物流小车                                 │
│  add all       — 每种类型各添加一台                           │
│  remove <id>   — 移除指定机器人 (例: remove drone-01)         │
│  list          — 列出所有机器人状态                           │
│  cmd <id> <action> — 向机器人发送重启指令                      │
│  help          — 显示此帮助                                   │
│  quit / q      — 退出                                        │
└─────────────────────────────────────────────────────────────┘
""")


def interactive_console(manager: MultiRobotManager):
    """交互式命令控制台。"""
    print_help()

    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd:
            continue

        parts = cmd.split()
        action = parts[0]

        if action in ('quit', 'q', 'exit'):
            break

        elif action == 'add':
            if len(parts) < 2:
                print("用法: add <drone|rover|rov|agv|all>")
                continue
            target = parts[1]
            if target == 'all':
                for t in ['drone', 'rover', 'rov', 'agv']:
                    rid = manager.add_robot(t)
                    if rid:
                        print(f"  ✅ 已添加 {rid}")
                print_status(manager)
            elif target in ROBOT_PROFILES:
                rid = manager.add_robot(target)
                if rid:
                    print(f"  ✅ 已添加 {rid}")
                    print_status(manager)
            else:
                print(f"未知类型: {target}，可选: drone, rover, rov, agv, all")

        elif action == 'remove':
            if len(parts) < 2:
                print("用法: remove <robot_id>")
                continue
            rid = parts[1]
            if manager.remove_robot(rid):
                print(f"  ✅ 已移除 {rid}")
            else:
                print(f"  ❌ 未找到机器人: {rid}")
            print_status(manager)

        elif action == 'list':
            print_status(manager)

        elif action == 'cmd':
            if len(parts) < 3:
                print("用法: cmd <robot_id> <action>")
                continue
            rid, action_cmd = parts[1], parts[2]
            bot = manager.get_robot(rid)
            if bot:
                bot._send({
                    'type': 'command_ack',
                    'command': {'action': action_cmd},
                    'status': 'manual',
                })
                print(f"  ✅ 已向 {rid} 发送: {action_cmd}")
            else:
                print(f"  ❌ 未找到: {rid}")

        elif action == 'help':
            print_help()

        else:
            print(f"未知命令: {action}，输入 help 查看帮助")


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='多机器人虚拟连接测试程序',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python mock_multi_robot_test.py                           # 本地测试，启动4台机器人
  python mock_multi_robot_test.py --count 2                 # 启动2台
  python mock_multi_robot_test.py --server 43.136.76.169 --proxy  # 连接远程服务器
  python mock_multi_robot_test.py --no-camera               # 禁用相机
  python mock_multi_robot_test.py --no-interactive          # 非交互模式（适合脚本）
        """,
    )
    parser.add_argument('--server', default='localhost', help='服务器地址（默认 localhost）')
    parser.add_argument('--port', type=int, default=8001, help='服务器端口（默认 8001）')
    parser.add_argument('--proxy', action='store_true', help='使用 Nginx 代理模式（端口 80）')
    parser.add_argument('--count', type=int, default=4, help='启动机器人数量（默认 4）')
    parser.add_argument('--no-camera', action='store_true', help='禁用相机模拟')
    parser.add_argument('--no-interactive', action='store_true', help='非交互模式')
    args = parser.parse_args()

    # 构建服务器 URL
    if args.proxy:
        server_url = f"ws://{args.server}"
    else:
        server_url = f"ws://{args.server}:{args.port}"

    enable_camera = not args.no_camera

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║            ROS Monitor — 多机器人虚拟测试程序                  ║
╠══════════════════════════════════════════════════════════════╣
║  服务器: {server_url:<49} ║
║  机器人: {args.count} 台 {'(相机模拟)' if enable_camera else '(无相机)'}                             ║
║  模式:   {'交互式' if not args.no_interactive else '自动运行'}{' ' * 57}║
╚══════════════════════════════════════════════════════════════╝
""")

    manager = MultiRobotManager(server_url, enable_camera)

    # 自动启动机器人
    types = ['drone', 'rover', 'rov', 'agv']
    for i in range(min(args.count, len(types))):
        t = types[i % len(types)]
        rid = manager.add_robot(t)
        if rid:
            time.sleep(0.5)  # 错开连接

    if manager.count == 0:
        print("❌ 没有机器人成功启动，请检查后端服务是否运行")
        sys.exit(1)

    time.sleep(1)
    print_status(manager)
    print(f"所有机器人已就绪！前端应能显示 {manager.count} 台机器人的选择器。\n")

    # 信号处理
    def shutdown(sig, frame):
        print("\n正在停止...")
        manager.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if args.no_interactive:
        # 非交互模式：运行直到 Ctrl+C
        print("非交互模式运行中，按 Ctrl+C 停止...\n")
        try:
            while True:
                time.sleep(5)
                print_status(manager)
        except KeyboardInterrupt:
            pass
    else:
        # 交互模式
        print("输入 help 查看命令列表\n")
        interactive_console(manager)

    manager.stop_all()
    print("再见！")


if __name__ == '__main__':
    main()
