#!/usr/bin/env python3
"""
机器人端数据推送代理 (ROS2 版)
==============================
运行在 ROS2 机器人上，通过 rclpy 订阅本地话题，
将传感器数据通过 WebSocket 推送到远程服务器。

用法:
    python3 robot_agent_ros2.py --server ws://43.136.76.169 --robot-id myrobot

依赖:
    - rclpy (ROS2 环境)
    - sensor_msgs, nav_msgs (ROS2 标准消息包)
    - sensor_msgs_py (ROS2 point_cloud2 工具)
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
                    format='[robot-agent-ros2] %(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger('robot_agent_ros2')

# ---- ROS2 依赖检测 ----
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
    from sensor_msgs.msg import PointCloud2, Imu, CompressedImage, NavSatFix
    from nav_msgs.msg import Path, Odometry
except ImportError as e:
    logger.error(f"ROS2 依赖缺失: {e}")
    logger.error("请先 source ROS2 环境: source /opt/ros/<distro>/setup.bash")
    sys.exit(1)

try:
    from sensor_msgs_py import point_cloud2 as pc2
except ImportError:
    logger.warning("sensor_msgs_py 未安装，尝试使用 sensor_msgs.point_cloud2")
    try:
        from sensor_msgs import point_cloud2 as pc2
    except ImportError:
        logger.error("point_cloud2 模块不可用，安装: pip install sensor-msgs-py")
        sys.exit(1)

try:
    import websocket
except ImportError:
    logger.error("websocket-client 未安装，执行: pip install websocket-client")
    sys.exit(1)


# ============================================================
# 消息解析器 —— 将 ROS2 消息对象转换为 JSON-serializable dict
# ============================================================

def _stamp_to_float(stamp) -> float:
    """ROS2 Time → 浮点秒"""
    return stamp.sec + stamp.nanosec * 1e-9


def parse_pointcloud2(msg: PointCloud2, max_points: int = 5000):
    """解析 sensor_msgs/PointCloud2 → 点坐标列表。"""
    points = []
    count = 0
    for pt in pc2.read_points(msg, field_names=('x', 'y', 'z'), skip_nans=True):
        points.append([float(pt[0]), float(pt[1]), float(pt[2])])
        count += 1
        if count >= max_points:
            break

    return {
        'timestamp': _stamp_to_float(msg.header.stamp),
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
        'timestamp': _stamp_to_float(msg.header.stamp),
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
        'timestamp': _stamp_to_float(msg.header.stamp),
        'encoding': msg.format,
        'data': base64.b64encode(msg.data).decode('utf-8'),
        'compressed': True,
    }


def parse_navsatfix(msg: NavSatFix):
    status = msg.status.status
    if status == 2:
        rtk = 'RTK_FIXED'
    elif status == 1:
        rtk = 'RTK_FLOAT'
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
        'time': {'week': 0, 'tow': _stamp_to_float(msg.header.stamp)},
        'timestamp': _stamp_to_float(msg.header.stamp),
        'sequence': 0,  # ROS2 移除了 header.seq
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
        'timestamp': _stamp_to_float(msg.header.stamp),
        'frame_id': msg.header.frame_id,
        'sequence': 0,  # ROS2 header 无 seq
        'total_poses': total,
        'sampled_poses': len(poses),
        'poses': poses,
    }


def parse_odometry(msg: Odometry):
    return {
        'timestamp': _stamp_to_float(msg.header.stamp),
        'frame_id': msg.header.frame_id,
        'child_frame_id': msg.child_frame_id,
        'sequence': 0,
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
# ROS2 节点 + WebSocket 代理
# ============================================================

class RobotAgentROS2(Node):
    """ROS2 节点：订阅话题 → WebSocket 推送到服务器。"""

    def __init__(self, server_url: str, robot_id: str):
        super().__init__('robot_monitor_agent')

        self.server_url = server_url.rstrip('/')
        self.robot_id = robot_id
        self.ws: Optional[websocket.WebSocketApp] = None
        self._running = False
        self._reconnect_delay = 3

        # 话题配置
        self.lidar_topic = '/livox/lidar'
        self.imu_topic = '/livox/imu'
        self.camera_topics = ['/left_camera/image/compressed', '/rgb_img/compressed']
        self.gnss_topic = '/ublox_driver/receiver_lla'
        self.path_topic = '/path'
        self.odom_topic = '/aft_mapped_to_init'
        self.cloud_topic = '/cloud_registered'

        # QoS：传感器数据用 BEST_EFFORT（兼容 Livox/Mid-360 默认 QoS）
        self._sensor_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        # 可靠传输用于路径/里程计
        self._reliable_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )

        logger.info(f"ROS2 节点已创建: robot_monitor_agent")

    # ---- WebSocket ----

    def _on_ws_open(self, ws):
        logger.info(f"已连接到服务器: {self.server_url}")
        hostname = socket.gethostname()
        local_ip = self._get_local_ip()
        self._send_json({
            'type': 'robot_register',
            'robot_id': self.robot_id,
            'hostname': hostname,
            'ip': local_ip,
            'ros_version': '2',
            'timestamp': time.time(),
        })

    def _on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('type') == 'robot_registered':
                logger.info(f"服务器确认注册: {data.get('message', '')}")
        except Exception:
            pass

    def _on_ws_error(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")

    def _on_ws_close(self, ws, close_code, close_msg):
        logger.warning(f"WebSocket 断开 (code={close_code})")
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
        t = threading.Thread(target=self.ws.run_forever, kwargs={'ping_interval': 30, 'ping_timeout': 10})
        t.daemon = True
        t.start()

    def _send_json(self, data: dict):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"发送失败: {e}")

    def _send_sensor(self, topic_type: str, topic_name: str, data: dict, **extra):
        msg = {
            'type': 'sensor_data',
            'topic': topic_type,
            'topic_name': topic_name,
            'data': data,
        }
        msg.update(extra)
        self._send_json(msg)

    # ---- ROS2 回调 ----

    def _on_lidar(self, msg: PointCloud2):
        payload = parse_pointcloud2(msg)
        self._send_sensor('lidar', self.lidar_topic, payload)

    def _on_imu(self, msg: Imu):
        self._send_sensor('imu', self.imu_topic, parse_imu(msg))

    def _on_gnss(self, msg: NavSatFix):
        self._send_sensor('gnss', self.gnss_topic, parse_navsatfix(msg))

    def _on_path(self, msg: Path):
        payload = parse_path(msg)
        payload['topic'] = self.path_topic
        self._send_sensor('slam_path', self.path_topic, payload)

    def _on_odometry(self, msg: Odometry):
        payload = parse_odometry(msg)
        payload['topic'] = self.odom_topic
        self._send_sensor('slam_odometry', self.odom_topic, payload)

    def _on_registered_cloud(self, msg: PointCloud2):
        parsed = parse_pointcloud2(msg, max_points=5000)
        payload = {
            'topic': self.cloud_topic,
            'timestamp': _stamp_to_float(msg.header.stamp),
            'frame_id': msg.header.frame_id,
            'sequence': 0,
            'total_points': msg.width * msg.height,
            'sampled_points': len(parsed['data']),
            'points': parsed['data'],
            'colors': [[255, 255, 255]] * len(parsed['data']),
            'has_rgb': False,
            'fields': ['x', 'y', 'z'],
        }
        self._send_sensor('slam_cloud', self.cloud_topic, payload)

    # ---- 初始化订阅 ----

    def setup_subscribers(self):
        """创建所有话题订阅。必须在 connect_ws 后调用。"""
        # LiDAR（BEST_EFFORT，兼容 Livox 驱动默认 QoS）
        self.create_subscription(
            PointCloud2, self.lidar_topic, self._on_lidar, self._sensor_qos)
        logger.info(f"已订阅 LiDAR: {self.lidar_topic}")

        # IMU
        self.create_subscription(
            Imu, self.imu_topic, self._on_imu, self._sensor_qos)
        logger.info(f"已订阅 IMU: {self.imu_topic}")

        # 相机（多路）
        for idx, topic in enumerate(self.camera_topics):
            camera_id = f'camera_{idx}'

            def make_cb(cid, t):
                return lambda msg: self._send_sensor(
                    'camera', t,
                    {**parse_compressed_image(msg), 'camera_id': cid, 'topic': t},
                    camera_id=cid,
                )
            self.create_subscription(
                CompressedImage, topic, make_cb(camera_id, topic), self._sensor_qos)
            logger.info(f"已订阅相机: {topic} (id={camera_id})")

        # GNSS
        self.create_subscription(
            NavSatFix, self.gnss_topic, self._on_gnss, self._sensor_qos)
        logger.info(f"已订阅 GNSS: {self.gnss_topic}")

        # SLAM
        self.create_subscription(
            Path, self.path_topic, self._on_path, self._reliable_qos)
        logger.info(f"已订阅 SLAM Path: {self.path_topic}")

        self.create_subscription(
            Odometry, self.odom_topic, self._on_odometry, self._reliable_qos)
        logger.info(f"已订阅 SLAM Odometry: {self.odom_topic}")

        self.create_subscription(
            PointCloud2, self.cloud_topic, self._on_registered_cloud, self._sensor_qos)
        logger.info(f"已订阅 SLAM Cloud: {self.cloud_topic}")

    # ---- 生命周期 ----

    def start(self):
        """启动代理。"""
        self._running = True
        self._connect_ws()
        time.sleep(1.5)  # 等 WebSocket 连接建立
        self.setup_subscribers()

        logger.info("========================================")
        logger.info(f"  机器人代理已启动 [{self.robot_id}] (ROS2)")
        logger.info(f"  服务器: {self.server_url}")
        logger.info(f"  IP: {self._get_local_ip()}")
        logger.info(f"  QoS: sensor={self._sensor_qos.reliability.name}")
        logger.info("  等待数据推送中...")
        logger.info("========================================")

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
    parser = argparse.ArgumentParser(description='ROS Monitor 机器人数据推送代理 (ROS2)')
    parser.add_argument('--server', default='ws://43.136.76.169',
                        help='服务器 WebSocket 地址')
    parser.add_argument('--robot-id', default=None,
                        help='机器人标识（默认: 主机名）')
    args = parser.parse_args()

    robot_id = args.robot_id or socket.gethostname()

    # 初始化 ROS2
    rclpy.init()

    agent = RobotAgentROS2(args.server, robot_id)
    agent.start()

    try:
        rclpy.spin(agent)
    except KeyboardInterrupt:
        logger.info("收到中断信号...")
    finally:
        agent.stop()
        agent.destroy_node()
        rclpy.shutdown()
        logger.info("ROS2 已关闭")


if __name__ == '__main__':
    logger.info("依赖: rclpy + sensor_msgs_py + websocket-client")
    logger.info("安装: pip install sensor-msgs-py websocket-client")
    main()
