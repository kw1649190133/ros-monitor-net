#!/usr/bin/env python3
"""
机器人端数据推送代理 (Robot Agent)
=============================
运行在 ROS 机器人上，通过 rospy 订阅本地话题，
将传感器数据通过 WebSocket 推送到远程服务器。

用法:
    python3 robot_agent.py --server ws://43.136.76.169 --robot-id myrobot

依赖:
    - rospy (系统 ROS 环境)
    - websocket-client (pip install websocket-client)
"""

import sys
import time
import json
import base64
import struct
import math
import signal
import socket
import argparse
import threading
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format='[robot-agent] %(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger('robot_agent')

# ---- 依赖检测 ----
try:
    import rospy
    from sensor_msgs.msg import PointCloud2, Imu, CompressedImage, NavSatFix
    from nav_msgs.msg import Path, Odometry
except ImportError as e:
    logger.error(f"ROS 依赖缺失: {e}")
    logger.error("请先 source ROS 环境: source /opt/ros/<distro>/setup.bash")
    sys.exit(1)

try:
    import websocket
except ImportError:
    logger.error("websocket-client 未安装，执行: pip install websocket-client")
    sys.exit(1)


# ============================================================
# 消息解析器 —— 将 ROS 消息对象转换为 JSON-serializable dict
# ============================================================

def _ros_time_to_float(stamp) -> float:
    return stamp.to_sec() if stamp else time.time()


def parse_pointcloud2(msg: PointCloud2, max_points: int = 5000):
    """解析 sensor_msgs/PointCloud2 → 点坐标列表。"""
    from sensor_msgs import point_cloud2 as pc2

    points = []
    count = 0
    for pt in pc2.read_points(msg, field_names=('x', 'y', 'z'), skip_nans=True):
        points.append([float(pt[0]), float(pt[1]), float(pt[2])])
        count += 1
        if count >= max_points:
            break

    return {
        'timestamp': _ros_time_to_float(msg.header.stamp),
        'frame_id': msg.header.frame_id,
        'point_count': len(points),
        'fields': [
            {'name': 'x', 'offset': 0, 'datatype': 7, 'count': 1},
            {'name': 'y', 'offset': 4, 'datatype': 7, 'count': 1},
            {'name': 'z', 'offset': 8, 'datatype': 7, 'count': 1},
        ],
        'data': points,
        'compression': 'none',
    }


def parse_imu(msg: Imu):
    return {
        'timestamp': _ros_time_to_float(msg.header.stamp),
        'orientation': {
            'x': msg.orientation.x, 'y': msg.orientation.y,
            'z': msg.orientation.z, 'w': msg.orientation.w,
        },
        'angular_velocity': {
            'x': msg.angular_velocity.x, 'y': msg.angular_velocity.y, 'z': msg.angular_velocity.z,
        },
        'linear_acceleration': {
            'x': msg.linear_acceleration.x, 'y': msg.linear_acceleration.y, 'z': msg.linear_acceleration.z,
        },
    }


def parse_compressed_image(msg: CompressedImage):
    return {
        'timestamp': _ros_time_to_float(msg.header.stamp),
        'encoding': msg.format,
        'data': base64.b64encode(msg.data).decode('utf-8'),
        'compressed': True,
    }


def parse_navsatfix(msg: NavSatFix):
    status = msg.status.status
    if status >= 2:
        rtk = 'RTK_FIXED' if status == 2 else 'RTK_FLOAT'
    elif status >= 0:
        rtk = 'GPS_3D'
    else:
        rtk = 'NO_FIX'

    cov = msg.position_covariance
    h_acc = math.sqrt(max(0, cov[0] + cov[4])) if len(cov) >= 5 else 0.0
    v_acc = math.sqrt(max(0, cov[8])) if len(cov) >= 9 else 0.0

    return {
        'rtk_status': rtk,
        'quality': {
            'fix_type': status, 'valid_fix': status >= 0,
            'diff_soln': status >= 1, 'carr_soln': 2 if status == 2 else 0,
            'num_sv': 0,
        },
        'position': {
            'latitude': round(msg.latitude, 8), 'longitude': round(msg.longitude, 8),
            'altitude': round(msg.altitude, 3), 'height_msl': round(msg.altitude, 3),
        },
        'accuracy': {
            'h_acc': round(h_acc, 4), 'v_acc': round(v_acc, 4),
            'p_dop': 0.0,
        },
        'velocity': {'vel_n': 0, 'vel_e': 0, 'vel_d': 0, 'vel_acc': 0},
        'time': {'week': 0, 'tow': _ros_time_to_float(msg.header.stamp)},
        'timestamp': _ros_time_to_float(msg.header.stamp),
        'sequence': getattr(msg.header, 'seq', 0),
    }


def parse_path(msg: Path, max_poses: int = 1000):
    total = len(msg.poses)
    step = max(1, total // max_poses) if total > max_poses else 1
    poses = []
    for i in range(0, total, step):
        p = msg.poses[i].pose
        poses.append({
            'position': {'x': p.position.x, 'y': p.position.y, 'z': p.position.z},
            'orientation': {'x': p.orientation.x, 'y': p.orientation.y,
                            'z': p.orientation.z, 'w': p.orientation.w},
        })
    return {
        'timestamp': _ros_time_to_float(msg.header.stamp),
        'frame_id': msg.header.frame_id,
        'sequence': msg.header.seq,
        'total_poses': total,
        'sampled_poses': len(poses),
        'poses': poses,
    }


def parse_odometry(msg: Odometry):
    return {
        'timestamp': _ros_time_to_float(msg.header.stamp),
        'frame_id': msg.header.frame_id,
        'child_frame_id': msg.child_frame_id,
        'sequence': msg.header.seq,
        'pose': {
            'position': {
                'x': msg.pose.pose.position.x, 'y': msg.pose.pose.position.y, 'z': msg.pose.pose.position.z,
            },
            'orientation': {
                'x': msg.pose.pose.orientation.x, 'y': msg.pose.pose.orientation.y,
                'z': msg.pose.pose.orientation.z, 'w': msg.pose.pose.orientation.w,
            },
        },
        'twist': {
            'linear': {'x': msg.twist.twist.linear.x, 'y': msg.twist.twist.linear.y, 'z': msg.twist.twist.linear.z},
            'angular': {'x': msg.twist.twist.angular.x, 'y': msg.twist.twist.angular.y, 'z': msg.twist.twist.angular.z},
        },
    }


# ============================================================
# 机器人代理主类
# ============================================================

class RobotAgent:
    """ROS 数据采集 + WebSocket 上报代理。"""

    def __init__(self, server_url: str, robot_id: str):
        self.server_url = server_url.rstrip('/')
        self.robot_id = robot_id
        self.ws: Optional[websocket.WebSocketApp] = None
        self._lock = threading.Lock()
        self._running = False
        self._reconnect_delay = 3
        self.frame_counts: dict = {}

        # 话题配置（与后端一致）
        self.lidar_topic = '/livox/lidar'
        self.imu_topic = '/livox/imu'
        self.camera_topics = ['/left_camera/image/compressed', '/rgb_img/compressed']
        self.gnss_topic = '/ublox_driver/receiver_lla'
        self.path_topic = '/path'
        self.odom_topic = '/aft_mapped_to_init'
        self.cloud_topic = '/cloud_registered'

    # ---- WebSocket 连接管理 ----

    def _on_ws_open(self, ws):
        logger.info(f"已连接到服务器: {self.server_url}")
        # 发送注册消息
        hostname = socket.gethostname()
        local_ip = self._get_local_ip()
        self._send({'type': 'robot_register', 'robot_id': self.robot_id,
                     'hostname': hostname, 'ip': local_ip,
                     'timestamp': time.time()})

    def _on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')
            if msg_type == 'robot_registered':
                logger.info(f"服务器确认注册: {data.get('message', '')}")
            elif msg_type == 'ping':
                self._send({'type': 'pong', 'timestamp': time.time()})
        except Exception:
            pass

    def _on_ws_error(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")

    def _on_ws_close(self, ws, close_code, close_msg):
        logger.warning(f"WebSocket 断开 (code={close_code}): {close_msg}")
        if self._running:
            logger.info(f"{self._reconnect_delay}s 后重连...")
            time.sleep(self._reconnect_delay)
            if self._running:
                self._connect_ws()

    def _connect_ws(self):
        ws_url = f"{self.server_url}/ws/robot/{self.robot_id}".replace('http://', 'ws://').replace('https://', 'wss://')
        logger.info(f"连接服务器: {ws_url}")
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
        )
        # 后台线程运行 WebSocket 事件循环
        t = threading.Thread(target=self.ws.run_forever, kwargs={'ping_interval': 30, 'ping_timeout': 10})
        t.daemon = True
        t.start()

    def _send(self, data: dict):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"发送失败: {e}")

    # ---- ROS 订阅回调 ----

    def _on_lidar(self, msg: PointCloud2):
        payload = parse_pointcloud2(msg)
        self._send({'type': 'sensor_data', 'topic': 'lidar', 'topic_name': self.lidar_topic, 'data': payload})

    def _on_imu(self, msg: Imu):
        payload = parse_imu(msg)
        self._send({'type': 'sensor_data', 'topic': 'imu', 'topic_name': self.imu_topic, 'data': payload})

    def _on_camera(self, msg: CompressedImage, camera_id: str, topic: str):
        payload = parse_compressed_image(msg)
        payload['camera_id'] = camera_id
        payload['topic'] = topic
        self._send({'type': 'sensor_data', 'topic': 'camera', 'topic_name': topic, 'data': payload,
                    'camera_id': camera_id})

    def _on_gnss(self, msg: NavSatFix):
        payload = parse_navsatfix(msg)
        self._send({'type': 'sensor_data', 'topic': 'gnss', 'topic_name': self.gnss_topic, 'data': payload})

    def _on_path(self, msg: Path):
        payload = parse_path(msg)
        payload['topic'] = self.path_topic
        self._send({'type': 'sensor_data', 'topic': 'slam_path', 'topic_name': self.path_topic, 'data': payload})

    def _on_odometry(self, msg: Odometry):
        payload = parse_odometry(msg)
        payload['topic'] = self.odom_topic
        self._send({'type': 'sensor_data', 'topic': 'slam_odometry', 'topic_name': self.odom_topic, 'data': payload})

    def _on_registered_cloud(self, msg: PointCloud2):
        points = parse_pointcloud2(msg, max_points=5000)
        payload = {
            'topic': self.cloud_topic,
            'timestamp': _ros_time_to_float(msg.header.stamp),
            'frame_id': msg.header.frame_id,
            'sequence': msg.header.seq,
            'total_points': msg.width * msg.height,
            'sampled_points': len(points['data']),
            'points': points['data'],
            'colors': [[255, 255, 255]] * len(points['data']),
            'has_rgb': False,
            'fields': ['x', 'y', 'z'],
        }
        self._send({'type': 'sensor_data', 'topic': 'slam_cloud', 'topic_name': self.cloud_topic, 'data': payload})

    # ---- 初始化 ----

    def start(self):
        """启动机器人代理：初始化 ROS 节点 + 连接服务器。"""
        self._running = True

        # 初始化 ROS 节点
        rospy.init_node('robot_monitor_agent', anonymous=True, disable_signals=True)
        logger.info(f"ROS 节点已初始化: robot_monitor_agent")

        # 连接服务器
        self._connect_ws()

        # 等待 WebSocket 连接建立
        time.sleep(1)

        # ---- 订阅话题 ----
        logger.info(f"订阅 LiDAR: {self.lidar_topic}")
        rospy.Subscriber(self.lidar_topic, PointCloud2, self._on_lidar, queue_size=1)

        logger.info(f"订阅 IMU: {self.imu_topic}")
        rospy.Subscriber(self.imu_topic, Imu, self._on_imu, queue_size=10)

        for idx, topic in enumerate(self.camera_topics):
            camera_id = f'camera_{idx}'
            logger.info(f"订阅相机: {topic} (id={camera_id})")
            rospy.Subscriber(topic, CompressedImage,
                             lambda msg, cid=camera_id, t=topic: self._on_camera(msg, cid, t),
                             queue_size=1)

        logger.info(f"订阅 GNSS: {self.gnss_topic}")
        rospy.Subscriber(self.gnss_topic, NavSatFix, self._on_gnss, queue_size=10)

        logger.info(f"订阅 SLAM Path: {self.path_topic}")
        rospy.Subscriber(self.path_topic, Path, self._on_path, queue_size=1)

        logger.info(f"订阅 SLAM Odometry: {self.odom_topic}")
        rospy.Subscriber(self.odom_topic, Odometry, self._on_odometry, queue_size=1)

        logger.info(f"订阅 SLAM Cloud: {self.cloud_topic}")
        rospy.Subscriber(self.cloud_topic, PointCloud2, self._on_registered_cloud, queue_size=1)

        logger.info("========================================")
        logger.info(f"  机器人代理已启动 [{self.robot_id}]")
        logger.info(f"  服务器: {self.server_url}")
        logger.info(f"  IP: {self._get_local_ip()}")
        logger.info("  等待数据推送中...")
        logger.info("========================================")

        # 保持主线程运行（rospy.spin 处理回调）
        rospy.spin()

    def stop(self):
        """停止代理。"""
        self._running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        logger.info("机器人代理已停止")

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
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='ROS Monitor 机器人数据推送代理')
    parser.add_argument('--server', default='ws://43.136.76.169',
                        help='服务器 WebSocket 地址（默认: ws://43.136.76.169，走 80 端口 Nginx 代理）')
    parser.add_argument('--robot-id', default=None,
                        help='机器人标识（默认: 自动使用主机名）')
    args = parser.parse_args()

    robot_id = args.robot_id or socket.gethostname()
    agent = RobotAgent(args.server, robot_id)

    def _shutdown(signum, frame):
        logger.info("收到退出信号，正在停止...")
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    agent.start()


if __name__ == '__main__':
    # 依赖检查说明
    logger.info("依赖: rospy (ROS 环境) + websocket-client (pip)")
    logger.info("安装: pip install websocket-client")
    main()
