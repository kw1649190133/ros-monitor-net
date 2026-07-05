#!/usr/bin/env python3
"""
模拟机器人数据推送 —— 用于测试服务器端到端管道。
从本地电脑生成假传感器数据，通过 WebSocket 推送到远程服务器。

用法:
    pip install websocket-client numpy opencv-python
    python mock_robot_test.py --server ws://43.136.76.169 --robot-id test-bot

    默认走 80 端口 Nginx 代理（推荐，外网可用）。
    如需直连 801 端口（仅内网可用）：加 --direct
    python mock_robot_test.py --server ws://43.136.76.169 --robot-id test-bot --direct
"""

import sys
import time
import json
import math
import base64
import random
import socket
import struct
import signal
import argparse
import threading
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format='[mock-robot] %(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger('mock_robot')

try:
    import websocket
except ImportError:
    logger.error("请安装: pip install websocket-client")
    sys.exit(1)

# 可选：生成测试图像需要 OpenCV
try:
    import numpy as np
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("OpenCV 未安装，相机数据将跳过（不影响其他传感器），安装: pip install opencv-python")


# ============================================================
# 假数据生成器
# ============================================================

class SensorSimulator:
    """生成模拟的 LiDAR / IMU / GNSS / SLAM 数据。"""

    def __init__(self):
        self._start_time = time.time()
        self._lidar_seq = 0
        self._imu_seq = 0
        self._gnss_seq = 0
        self._camera_seq = 0

        self.base_lat = 39.0790108   # 北京
        self.base_lon = 117.7151327
        self.base_alt = -2.5

        # 预生成一个球形点云（静止场景）
        self._sphere_points = self._make_sphere(radius=5.0, n_points=3000)

    def elapsed(self) -> float:
        return time.time() - self._start_time

    @staticmethod
    def _make_sphere(radius: float, n_points: int):
        """生成球面点云。"""
        pts = []
        for _ in range(n_points):
            theta = random.random() * 2 * math.pi
            phi = math.acos(2 * random.random() - 1)
            x = radius * math.sin(phi) * math.cos(theta)
            y = radius * math.sin(phi) * math.sin(theta)
            z = radius * math.cos(phi)
            pts.append([x, y, z])
        return pts

    # ---- LiDAR ----

    def generate_lidar(self) -> dict:
        self._lidar_seq += 1
        t = self.elapsed()

        # 让点云绕 Z 轴缓慢旋转，模拟扫描
        angle = t * 0.3  # 0.3 rad/s
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        rotated = []
        for x, y, z in self._sphere_points:
            rx = x * cos_a - y * sin_a
            ry = x * sin_a + y * cos_a
            rotated.append([round(rx, 4), round(ry, 4), round(z, 4)])

        # 加一点噪声
        noisy = [[p[0]+random.uniform(-0.05,0.05),
                  p[1]+random.uniform(-0.05,0.05),
                  p[2]+random.uniform(-0.02,0.02)] for p in rotated]

        return {
            'timestamp': t,
            'frame_id': 'livox_frame',
            'point_count': min(5000, len(noisy)),
            'fields': [
                {'name': 'x', 'offset': 0, 'datatype': 7, 'count': 1},
                {'name': 'y', 'offset': 4, 'datatype': 7, 'count': 1},
                {'name': 'z', 'offset': 8, 'datatype': 7, 'count': 1},
            ],
            'data': noisy[:5000],
            'compression': 'none',
        }

    # ---- IMU ----

    def generate_imu(self) -> dict:
        self._imu_seq += 1
        t = self.elapsed()

        # 模拟手持设备的小幅晃动
        roll  = math.sin(t * 0.5) * 0.1
        pitch = math.cos(t * 0.7) * 0.08
        yaw   = t * 0.1

        cy, sy = math.cos(yaw/2), math.sin(yaw/2)
        cp, sp = math.cos(pitch/2), math.sin(pitch/2)
        cr, sr = math.cos(roll/2), math.sin(roll/2)

        qw = cr*cp*cy + sr*sp*sy
        qx = sr*cp*cy - cr*sp*sy
        qy = cr*sp*cy + sr*cp*sy
        qz = cr*cp*sy - sr*sp*cy

        return {
            'timestamp': t,
            'orientation': {
                'x': round(qx, 6), 'y': round(qy, 6),
                'z': round(qz, 6), 'w': round(qw, 6),
            },
            'angular_velocity': {
                'x': round(math.cos(t*0.5)*0.2, 6),
                'y': round(math.sin(t*0.7)*0.15, 6),
                'z': round(random.uniform(-0.05, 0.05), 6),
            },
            'linear_acceleration': {
                'x': round(random.uniform(-0.3, 0.3), 6),
                'y': round(random.uniform(-0.2, 0.2), 6),
                'z': round(9.8 + random.uniform(-0.1, 0.1), 6),
            },
        }

    # ---- Camera ----

    def generate_camera(self, camera_id: str) -> Optional[dict]:
        if not HAS_CV2:
            return None

        self._camera_seq += 1
        t = self.elapsed()

        # 生成 640x480 的测试图像，带时间戳文字
        img = np.zeros((360, 480, 3), dtype=np.uint8)
        # 背景渐变
        for i in range(360):
            color = int(40 + i * 0.3)
            cv2.line(img, (0, i), (480, i), (color, color//2, color), 1)
        # 中心十字线
        cv2.line(img, (240, 0), (240, 360), (0, 255, 0), 1)
        cv2.line(img, (0, 180), (480, 180), (0, 255, 0), 1)
        # 信息文字
        cv2.putText(img, f'Mock Camera [{camera_id}]', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Frame: {self._camera_seq}', (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(img, f'Time: {t:.1f}s', (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        # 移动的圆点
        cx = int(240 + math.sin(t * 2) * 150)
        cy = int(180 + math.cos(t * 3) * 100)
        cv2.circle(img, (cx, cy), 15, (0, 0, 255), -1)

        _, jpeg_data = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        jpeg_b64 = base64.b64encode(jpeg_data).decode('utf-8')

        return {
            'camera_id': camera_id,
            'topic': f'/mock/{camera_id}/image/compressed',
            'timestamp': t,
            'encoding': 'jpeg',
            'width': 480,
            'height': 360,
            'data': jpeg_b64,
            'compressed': True,
            'sequence': self._camera_seq,
        }

    # ---- GNSS ----

    def generate_gnss(self) -> dict:
        self._gnss_seq += 1
        t = self.elapsed()

        # 模拟 RTK_FIXED 状态，缓慢漂移
        drift_lat = math.sin(t * 0.05) * 0.00002
        drift_lon = math.cos(t * 0.05) * 0.00002
        drift_alt = math.sin(t * 0.1) * 0.3

        statuses = ['RTK_FIXED', 'RTK_FIXED', 'RTK_FIXED', 'RTK_FLOAT']  # 大部分时间 RTK_FIXED
        rtk = random.choice(statuses)

        return {
            'rtk_status': rtk,
            'quality': {
                'fix_type': 3, 'valid_fix': True,
                'diff_soln': True,
                'carr_soln': 2 if rtk == 'RTK_FIXED' else 1,
                'num_sv': random.randint(12, 28),
            },
            'position': {
                'latitude': round(self.base_lat + drift_lat + random.uniform(-1e-7, 1e-7), 8),
                'longitude': round(self.base_lon + drift_lon + random.uniform(-1e-7, 1e-7), 8),
                'altitude': round(self.base_alt + drift_alt + random.uniform(-0.05, 0.05), 3),
                'height_msl': round(self.base_alt + 7.0 + random.uniform(-0.05, 0.05), 3),
            },
            'accuracy': {
                'h_acc': round(random.uniform(0.008, 0.02), 4),
                'v_acc': round(random.uniform(0.01, 0.03), 4),
                'p_dop': round(random.uniform(0.5, 1.5), 2),
            },
            'velocity': {
                'vel_n': round(random.uniform(-0.3, 0.3), 3),
                'vel_e': round(random.uniform(-0.3, 0.3), 3),
                'vel_d': round(random.uniform(-0.05, 0.05), 3),
                'vel_acc': round(random.uniform(0.1, 0.2), 3),
            },
            'time': {'week': 2393, 'tow': t},
            'timestamp': t,
            'sequence': self._gnss_seq,
        }

    # ---- SLAM ----

    def generate_path(self) -> dict:
        """生成螺旋轨迹。"""
        t = self.elapsed()
        poses = []
        for i in range(200):
            r = i * 0.15
            angle = t * 0.2 + i * 0.08
            poses.append({
                'position': {
                    'x': round(r * math.cos(angle), 3),
                    'y': round(r * math.sin(angle), 3),
                    'z': round(i * 0.01, 3),
                },
                'orientation': {
                    'x': 0.0, 'y': 0.0,
                    'z': round(math.sin(angle/2), 4),
                    'w': round(math.cos(angle/2), 4),
                },
            })
        return {
            'topic': '/path',
            'timestamp': t,
            'frame_id': 'map',
            'sequence': 0,
            'total_poses': len(poses),
            'sampled_poses': len(poses),
            'poses': poses,
        }

    def generate_odometry(self) -> dict:
        """沿圆运动的里程计。"""
        t = self.elapsed()
        radius = 10.0
        ang = t * 0.2
        x = radius * math.cos(ang)
        y = radius * math.sin(ang)

        return {
            'topic': '/aft_mapped_to_init',
            'timestamp': t,
            'frame_id': 'map',
            'child_frame_id': 'base_link',
            'sequence': 0,
            'pose': {
                'position': {'x': round(x, 3), 'y': round(y, 3), 'z': 0.0},
                'orientation': {
                    'x': 0.0, 'y': 0.0,
                    'z': round(math.sin((ang + math.pi/2)/2), 4),
                    'w': round(math.cos((ang + math.pi/2)/2), 4),
                },
            },
            'twist': {
                'linear': {'x': 0.0, 'y': round(radius*0.2, 3), 'z': 0.0},
                'angular': {'x': 0.0, 'y': 0.0, 'z': 0.2},
            },
        }

    def generate_registered_cloud(self) -> dict:
        """累积点云地图。"""
        t = self.elapsed()
        # 6 个"墙面"的平面点
        pts = []
        colors = []
        walls = [
            (0, 5, -2, 2, (255, 100, 100)),   # 前墙
            (5, 0, -2, 2, (100, 255, 100)),   # 右墙
            (0, -5, -2, 2, (100, 100, 255)),   # 后墙
            (-5, 0, -2, 2, (255, 255, 100)),   # 左墙
            (0, 0, 2, 1, (200, 200, 200)),     # 天花板
            (0, 0, -2, -1, (100, 100, 100)),   # 地板
        ]
        for wx, wy, z0, z1, color in walls:
            for _ in range(400):
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

        # 加一些扫描线（模拟 LiDAR 扫描）
        ang = t * 0.5
        for i in range(500):
            r = random.uniform(1, 6)
            a = ang + random.uniform(-0.5, 0.5)
            pts.append([round(r*math.cos(a), 3), round(r*math.sin(a), 3), round(random.uniform(-1, 2), 3)])
            colors.append([255, 50, 50])

        return {
            'topic': '/cloud_registered',
            'timestamp': t,
            'frame_id': 'map',
            'sequence': 0,
            'total_points': len(pts),
            'sampled_points': len(pts),
            'points': pts,
            'colors': colors,
            'has_rgb': True,
            'fields': ['x', 'y', 'z', 'rgb'],
        }


# ============================================================
# 模拟机器人 — WebSocket 连接 + 定时推送
# ============================================================

class MockRobot:
    """模拟机器人：连接服务器 → 注册 → 循环推送数据。"""

    def __init__(self, server_host: str, robot_id: str, proxy: bool = True):
        """初始化模拟机器人。

        Args:
            server_host: 服务器地址（如 43.136.76.169）
            robot_id: 机器人标识
            proxy: True=走 80 端口 Nginx，False=直连 801
        """
        if proxy:
            # 走 80 端口 Nginx 代理（推荐，外网可用）
            self.ws_url = f"ws://{server_host}/ws/robot/{robot_id}"
        else:
            # 直连 801 端口（仅内网可用）
            self.ws_url = f"ws://{server_host}:801/ws/robot/{robot_id}"

        self.robot_id = robot_id
        self.ws: Optional[websocket.WebSocketApp] = None
        self.sim = SensorSimulator()
        self._running = False
        self._push_interval = 0.1  # 10Hz

    def _on_open(self, ws):
        logger.info(f"已连接: {self.ws_url}")
        # 注册
        self._send({
            'type': 'robot_register',
            'robot_id': self.robot_id,
            'hostname': socket.gethostname(),
            'ip': self._get_local_ip(),
            'ros_version': 'mock',
            'timestamp': time.time(),
        })

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('type') == 'robot_registered':
                logger.info(f"服务器确认注册: {data.get('message', '')}")
        except Exception:
            pass

    def _on_error(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")

    def _on_close(self, ws, code, msg):
        logger.warning(f"连接断开 (code={code})")
        if self._running:
            time.sleep(3)
            self._connect()

    def _connect(self):
        logger.info(f"连接目标: {self.ws_url}")
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        t = threading.Thread(target=self.ws.run_forever, kwargs={'ping_interval': 30})
        t.daemon = True
        t.start()

    def _send(self, data: dict):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"发送失败: {e}")

    def _push_sensor(self, topic_type: str, topic_name: str, data: dict, **extra):
        msg = {'type': 'sensor_data', 'topic': topic_type, 'topic_name': topic_name, 'data': data}
        msg.update(extra)
        self._send(msg)

    def _push_loop(self):
        """定时推送所有传感器数据。"""
        logger.info("开始推送模拟数据 (10Hz)...")
        frame = 0

        while self._running:
            try:
                t0 = time.time()

                # LiDAR (每帧都发)
                self._push_sensor('lidar', '/livox/lidar', self.sim.generate_lidar())

                # IMU
                if frame % 1 == 0:
                    self._push_sensor('imu', '/livox/imu', self.sim.generate_imu())

                # Camera (每 5 帧发一次，降低带宽)
                if frame % 5 == 0:
                    left = self.sim.generate_camera('left_camera')
                    if left:
                        self._push_sensor('camera', '/left_camera/image/compressed', left, camera_id='left_camera')
                    right = self.sim.generate_camera('right_camera')
                    if right:
                        self._push_sensor('camera', '/rgb_img/compressed', right, camera_id='right_camera')

                # GNSS (每秒)
                if frame % 10 == 0:
                    self._push_sensor('gnss', '/ublox_driver/receiver_lla', self.sim.generate_gnss())

                # SLAM (每 2 帧)
                if frame % 2 == 0:
                    self._push_sensor('slam_path', '/path', self.sim.generate_path())
                    self._push_sensor('slam_odometry', '/aft_mapped_to_init', self.sim.generate_odometry())
                    self._push_sensor('slam_cloud', '/cloud_registered', self.sim.generate_registered_cloud())

                frame += 1

                # 控制推送频率
                elapsed = time.time() - t0
                sleep_time = max(0, self._push_interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"推送循环异常: {e}")
                time.sleep(1)

    def start(self):
        self._running = True
        self._connect()
        time.sleep(1.5)  # 等连接建立
        self._push_loop()

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

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
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='模拟 ROS 机器人数据推送测试')
    parser.add_argument('--server', default='43.136.76.169',
                        help='服务器地址（默认: 43.136.76.169）')
    parser.add_argument('--robot-id', default='mock-bot-01',
                        help='机器人标识（默认: mock-bot-01）')
    parser.add_argument('--direct', action='store_true',
                        help='直连 801 端口（默认走 80 端口 Nginx 代理）')
    args = parser.parse_args()

    proxy = not args.direct
    bot = MockRobot(args.server, args.robot_id, proxy=proxy)

    logger.info(f"连接模式: {'Nginx 代理 (port 80)' if proxy else '直连 (port 801)'}")
    logger.info(f"连接目标: {bot.ws_url}")
    logger.info(f"机器人 ID: {args.robot_id}")
    logger.info("按 Ctrl+C 停止")

    def shutdown(sig, frame):
        logger.info("正在停止...")
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    bot.start()


if __name__ == '__main__':
    main()
