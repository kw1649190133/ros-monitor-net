"""
ROS 节点管理器（rosbridge 版）
通过 rosbridge WebSocket 远程订阅 ROS topic，替代本地 rospy 直连。
"""

import asyncio
import logging
import time
import os
import threading
from functools import partial
from typing import Dict, Any, Optional

from src.ros_bridge.rosbridge_client import RosbridgeClient
from src.ros_bridge.pointcloud_parser import parse_pointcloud2
from src.utils.camera_config_loader import camera_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topic 消息处理器 —— 将 rosbridge JSON 解析为前端需要的 dict 格式
# ---------------------------------------------------------------------------

def _handle_lidar(callback, topic: str, msg: dict) -> None:
    """处理 /livox/lidar PointCloud2 消息。"""
    points, colors, total_points = parse_pointcloud2(msg, max_points=5000)
    payload = {
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'frame_id': msg.get('header', {}).get('frame_id', ''),
        'point_count': len(points),
        'fields': [
            {'name': 'x', 'offset': 0, 'datatype': 7, 'count': 1},
            {'name': 'y', 'offset': 4, 'datatype': 7, 'count': 1},
            {'name': 'z', 'offset': 8, 'datatype': 7, 'count': 1},
        ],
        'data': points,
        'compression': 'none',
    }
    callback(payload)


def _handle_imu(callback, topic: str, msg: dict) -> None:
    """处理 /livox/imu sensor_msgs/Imu 消息。"""
    payload = {
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'orientation': {
            'x': msg.get('orientation', {}).get('x', 0.0),
            'y': msg.get('orientation', {}).get('y', 0.0),
            'z': msg.get('orientation', {}).get('z', 0.0),
            'w': msg.get('orientation', {}).get('w', 1.0),
        },
        'angular_velocity': {
            'x': msg.get('angular_velocity', {}).get('x', 0.0),
            'y': msg.get('angular_velocity', {}).get('y', 0.0),
            'z': msg.get('angular_velocity', {}).get('z', 0.0),
        },
        'linear_acceleration': {
            'x': msg.get('linear_acceleration', {}).get('x', 0.0),
            'y': msg.get('linear_acceleration', {}).get('y', 0.0),
            'z': msg.get('linear_acceleration', {}).get('z', 0.0),
        },
    }
    callback(payload)


# 模块级 GNSS 序列计数器（替代函数属性的可变全局状态）
_gnss_seq = {'pvt': 0, 'navsatfix': 0}


def _handle_gnss_pvt(callback, topic: str, msg: dict) -> None:
    """处理 gnss_comm/GnssPVTSolnMsg 消息。"""
    rtk_status = _resolve_gnss_status(msg)
    payload = {
        'rtk_status': rtk_status,
        'quality': {
            'fix_type': msg.get('fix_type', 0),
            'valid_fix': msg.get('valid_fix', False),
            'diff_soln': msg.get('diff_soln', False),
            'carr_soln': msg.get('carr_soln', 0),
            'num_sv': msg.get('num_sv', 0),
        },
        'position': {
            'latitude': round(msg.get('latitude', 0.0), 8),
            'longitude': round(msg.get('longitude', 0.0), 8),
            'altitude': round(msg.get('altitude', 0.0), 3),
            'height_msl': round(msg.get('height_msl', 0.0), 3),
        },
        'accuracy': {
            'h_acc': round(msg.get('h_acc', 0.0), 4),
            'v_acc': round(msg.get('v_acc', 0.0), 4),
            'p_dop': round(msg.get('p_dop', 0.0), 2),
        },
        'velocity': {
            'vel_n': round(msg.get('vel_n', 0.0), 3),
            'vel_e': round(msg.get('vel_e', 0.0), 3),
            'vel_d': round(msg.get('vel_d', 0.0), 3),
            'vel_acc': round(msg.get('vel_acc', 0.0), 3),
        },
        'time': {
            'week': msg.get('time', {}).get('week', 0),
            'tow': round(msg.get('time', {}).get('tow', 0.0), 1),
        },
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'sequence': _gnss_seq['pvt'],
    }
    _gnss_seq['pvt'] += 1
    callback(payload)


def _handle_navsatfix(callback, topic: str, msg: dict) -> None:
    """处理 sensor_msgs/NavSatFix 消息。"""
    status = msg.get('status', {}).get('status', -1)
    if status == 2:
        rtk_status = 'RTK_FIXED'
    elif status >= 0:
        rtk_status = 'GPS_3D'
    else:
        rtk_status = 'NO_FIX'

    cov = msg.get('position_covariance', [0] * 9)
    import math
    e_var = cov[0] if len(cov) > 0 else 0
    n_var = cov[4] if len(cov) > 4 else 0
    u_var = cov[8] if len(cov) > 8 else 0
    h_acc = math.sqrt(max(0, e_var + n_var)) if (e_var > 0 or n_var > 0) else 0.0
    v_acc = math.sqrt(max(0, u_var)) if u_var > 0 else 0.0

    payload = {
        'rtk_status': rtk_status,
        'quality': {
            'fix_type': 3 if status >= 0 else 0,
            'valid_fix': status >= 0,
            'diff_soln': status >= 1,
            'carr_soln': 2 if status == 2 else 0,
            'num_sv': 0,
        },
        'position': {
            'latitude': round(msg.get('latitude', 0.0), 8),
            'longitude': round(msg.get('longitude', 0.0), 8),
            'altitude': round(msg.get('altitude', 0.0), 3),
            'height_msl': round(msg.get('altitude', 0.0), 3),
        },
        'accuracy': {
            'h_acc': round(h_acc, 4),
            'v_acc': round(v_acc, 4),
            'p_dop': round(math.sqrt(h_acc ** 2 + v_acc ** 2) if (h_acc > 0 or v_acc > 0) else 0.0, 2),
        },
        'velocity': {'vel_n': 0.0, 'vel_e': 0.0, 'vel_d': 0.0, 'vel_acc': 0.0},
        'time': {'week': 0, 'tow': msg.get('header', {}).get('stamp', {}).get('secs', time.time())},
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'sequence': _gnss_seq['navsatfix'],
    }
    _gnss_seq['navsatfix'] += 1
    callback(payload)


def _handle_path(callback, topic: str, msg: dict) -> None:
    """处理 nav_msgs/Path 消息。"""
    poses_raw = msg.get('poses', [])
    total_poses = len(poses_raw)
    max_points = 1000
    step = max(1, total_poses // max_points) if total_poses > max_points else 1

    poses = []
    for i in range(0, total_poses, step):
        p = poses_raw[i]
        pose = p.get('pose', {})
        poses.append({
            'position': {
                'x': float(pose.get('position', {}).get('x', 0)),
                'y': float(pose.get('position', {}).get('y', 0)),
                'z': float(pose.get('position', {}).get('z', 0)),
            },
            'orientation': {
                'x': float(pose.get('orientation', {}).get('x', 0)),
                'y': float(pose.get('orientation', {}).get('y', 0)),
                'z': float(pose.get('orientation', {}).get('z', 0)),
                'w': float(pose.get('orientation', {}).get('w', 1)),
            },
        })

    payload = {
        'topic': topic,
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'frame_id': msg.get('header', {}).get('frame_id', ''),
        'sequence': msg.get('header', {}).get('seq', 0),
        'total_poses': total_poses,
        'sampled_poses': len(poses),
        'poses': poses,
    }
    callback(payload)


def _handle_odometry(callback, topic: str, msg: dict) -> None:
    """处理 nav_msgs/Odometry 消息。"""
    pose = msg.get('pose', {}).get('pose', {})
    twist = msg.get('twist', {}).get('twist', {})
    payload = {
        'topic': topic,
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'frame_id': msg.get('header', {}).get('frame_id', ''),
        'child_frame_id': msg.get('child_frame_id', ''),
        'sequence': msg.get('header', {}).get('seq', 0),
        'pose': {
            'position': {
                'x': float(pose.get('position', {}).get('x', 0)),
                'y': float(pose.get('position', {}).get('y', 0)),
                'z': float(pose.get('position', {}).get('z', 0)),
            },
            'orientation': {
                'x': float(pose.get('orientation', {}).get('x', 0)),
                'y': float(pose.get('orientation', {}).get('y', 0)),
                'z': float(pose.get('orientation', {}).get('z', 0)),
                'w': float(pose.get('orientation', {}).get('w', 1)),
            },
        },
        'twist': {
            'linear': {
                'x': float(twist.get('linear', {}).get('x', 0)),
                'y': float(twist.get('linear', {}).get('y', 0)),
                'z': float(twist.get('linear', {}).get('z', 0)),
            },
            'angular': {
                'x': float(twist.get('angular', {}).get('x', 0)),
                'y': float(twist.get('angular', {}).get('y', 0)),
                'z': float(twist.get('angular', {}).get('z', 0)),
            },
        },
    }
    callback(payload)


def _handle_registered_cloud(callback, topic: str, msg: dict) -> None:
    """处理 /cloud_registered PointCloud2 消息。"""
    points, colors, total_points = parse_pointcloud2(msg, max_points=5000)
    field_names = [f.get('name', '') for f in msg.get('fields', [])]
    has_rgb = 'rgb' in field_names

    payload = {
        'topic': topic,
        'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', time.time()),
        'frame_id': msg.get('header', {}).get('frame_id', ''),
        'sequence': msg.get('header', {}).get('seq', 0),
        'total_points': total_points,
        'sampled_points': len(points),
        'points': points,
        'colors': colors or [[255, 255, 255]] * len(points),
        'has_rgb': has_rgb,
        'fields': ['x', 'y', 'z', 'rgb'] if has_rgb else ['x', 'y', 'z'],
    }
    callback(payload)


def _resolve_gnss_status(msg: dict) -> str:
    """根据 carr_soln / fix_type 解析 RTK 状态字符串。"""
    carr = msg.get('carr_soln', 0)
    fix = msg.get('fix_type', 0)
    if carr == 2:
        return 'RTK_FIXED'
    if carr == 1:
        return 'RTK_FLOAT'
    if fix == 3:
        return 'GPS_3D'
    if fix == 2:
        return 'GPS_2D'
    if fix == 1:
        return 'GPS_1D'
    return 'NO_FIX'


# ---------------------------------------------------------------------------
# 相机消息处理器（有状态，需要独立类）
# ---------------------------------------------------------------------------

class _CameraHandler:
    """压缩图像处理器，保持帧计数和图像参数。"""

    def __init__(self, topic: str, camera_id: str = None,
                 image_params: dict = None):
        self.topic = topic
        self.frame_count = 0
        self.last_frame_time = 0.0
        self.is_active = True

        if camera_id:
            self.camera_id = camera_id
        elif 'left_camera' in topic:
            self.camera_id = 'left_camera'
        elif 'right_camera' in topic:
            self.camera_id = 'right_camera'
        else:
            parts = topic.split('/')
            self.camera_id = parts[-3] if 'compressed' in parts[-1] and len(parts) >= 3 else 'unknown'

        if image_params:
            self.jpeg_quality = image_params.get('jpeg_quality', 70)
            self.max_width = image_params.get('max_width', 640)
            self.enable_resize = image_params.get('enable_resize', True)
        else:
            self.jpeg_quality = 70
            self.max_width = 640
            self.enable_resize = True

        logger.info(f"相机处理器创建: topic={topic}, camera_id={self.camera_id}")

    def __call__(self, callback, topic: str, msg: dict) -> None:
        """rosbridge 回调入口。"""
        try:
            import base64
            import numpy as np
            import cv2

            now = time.time()
            fmt = msg.get('format', 'jpeg')
            data_b64 = msg.get('data', '')

            if not data_b64:
                return

            jpeg_bytes = base64.b64decode(data_b64)
            np_arr = np.frombuffer(jpeg_bytes, np.uint8)
            cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if cv_image is None:
                return

            # 缩放
            if self.enable_resize and cv_image.shape[1] > self.max_width:
                scale = self.max_width / cv_image.shape[1]
                new_h = int(cv_image.shape[0] * scale)
                cv_image = cv2.resize(cv_image, (self.max_width, new_h))

            # 重新编码为 JPEG
            _, jpeg_buf = cv2.imencode('.jpg', cv_image,
                                       [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            jpeg_b64 = base64.b64encode(jpeg_buf).decode('utf-8')

            camera_data = {
                'camera_id': self.camera_id,
                'topic': self.topic,
                'timestamp': msg.get('header', {}).get('stamp', {}).get('secs', now),
                'sequence': self.frame_count,
                'encoding': 'jpeg',
                'width': cv_image.shape[1],
                'height': cv_image.shape[0],
                'data': jpeg_b64,
                'compressed': True,
                'compressed_size': len(jpeg_b64),
                'compression_ratio': len(jpeg_b64) / (cv_image.shape[0] * cv_image.shape[1] * 3) * 100,
                'frame_rate': 1.0 / (now - self.last_frame_time) if self.last_frame_time > 0 else 0.0,
            }

            callback(camera_data)
            self.frame_count += 1
            self.last_frame_time = now

        except Exception as e:
            logger.error(f"[{self.topic}] 相机处理错误: {e}")

    def update_settings(self, preview_height=None, jpeg_quality=None):
        if preview_height is not None:
            self.max_width = int(preview_height * 4 / 3)
        if jpeg_quality is not None:
            self.jpeg_quality = max(1, min(100, jpeg_quality))

    def get_status(self) -> dict:
        return {
            'topic': self.topic,
            'camera_id': self.camera_id,
            'is_active': self.is_active,
            'frame_count': self.frame_count,
            'last_frame_time': self.last_frame_time,
        }


# ---------------------------------------------------------------------------
# ROSNodeManager（rosbridge 重构版）
# ---------------------------------------------------------------------------

class ROSNodeManager:
    """ROS 节点管理器 —— 通过 rosbridge 远程订阅 topic。

    支持多机器人：latest_data 改为 {robot_id: {topic: data}}。
    向后兼容：不带 robot_id 时返回第一个机器人的数据。

    环境变量:
        ROSBRIDGE_HOST: rosbridge 服务器 IP（默认 localhost）
        ROSBRIDGE_PORT: rosbridge 端口（默认 9090）
    """

    def __init__(self):
        self.subscribers: Dict[str, Any] = {}
        self.robot_data: Dict[str, Dict[str, Any]] = {}   # {robot_id: {topic: entry}}
        self._lock = threading.Lock()
        self._running = False
        self._initialized = False

        rosbridge_host = os.getenv('ROSBRIDGE_HOST', 'localhost')
        rosbridge_port = int(os.getenv('ROSBRIDGE_PORT', '9090'))
        self.rosbridge = RosbridgeClient(host=rosbridge_host, port=rosbridge_port)

        # 话题配置
        self.camera_topics = camera_config.get_topic_list()
        self.image_params = camera_config.get_image_processing_params()
        self.lidar_topics = ['/livox/lidar']
        self.imu_topics = ['/livox/imu']
        self.gnss_topics = [
            {'topic': '/ublox_driver/receiver_pvt', 'type': 'GnssPVTSolnMsg'},
            {'topic': '/ublox_driver/receiver_lla', 'type': 'NavSatFix'},
        ]
        self.slam_topics = {
            'path': '/path',
            'odometry': '/aft_mapped_to_init',
            'registered_cloud': '/cloud_registered',
        }

        logger.info(f"ROSNodeManager 初始化: rosbridge -> ws://{rosbridge_host}:{rosbridge_port}")

    async def initialize(self):
        """连接到 rosbridge 并订阅所有话题。"""
        try:
            logger.info("正在连接到 rosbridge...")
            await self.rosbridge.connect()
            logger.info("rosbridge 连接成功，开始设置订阅...")
            self._setup_subscribers()
            self._running = True
            self._initialized = True
            logger.info(f"ROSNodeManager 初始化完成，已订阅 {len(self.subscribers)} 个话题")
        except Exception as e:
            logger.error(f"ROS 初始化失败: {e}")
            raise

    def _setup_subscribers(self):
        """通过 rosbridge 订阅所有话题。"""
        subscribed = 0

        # --- 相机 ---
        for topic in self.camera_topics:
            camera_id = camera_config.get_camera_id_by_topic(topic)
            handler = _CameraHandler(topic, camera_id, self.image_params)
            _cam_cb = partial(handler, self._update_data, topic)
            try:
                self.rosbridge.subscribe(topic, 'sensor_msgs/CompressedImage', _cam_cb)
                self.subscribers[topic] = handler
                subscribed += 1
                logger.info(f"  相机订阅成功: {topic} (camera_id={camera_id})")
            except Exception as e:
                logger.warning(f"  相机订阅失败 {topic}: {e}")

        # --- 激光雷达 ---
        for topic in self.lidar_topics:
            _lidar_cb = partial(_handle_lidar, self._update_data, topic)
            try:
                self.rosbridge.subscribe(topic, 'sensor_msgs/PointCloud2', _lidar_cb)
                self.subscribers[topic] = {'topic': topic, 'type': 'lidar', 'active': True}
                subscribed += 1
                logger.info(f"  激光雷达订阅成功: {topic}")
            except Exception as e:
                logger.warning(f"  激光雷达订阅失败 {topic}: {e}")

        # --- IMU ---
        for topic in self.imu_topics:
            _imu_cb = partial(_handle_imu, self._update_data, topic)
            try:
                self.rosbridge.subscribe(topic, 'sensor_msgs/Imu', _imu_cb)
                self.subscribers[topic] = {'topic': topic, 'type': 'imu', 'active': True}
                subscribed += 1
                logger.info(f"  IMU 订阅成功: {topic}")
            except Exception as e:
                logger.warning(f"  IMU 订阅失败 {topic}: {e}")

        # --- GNSS（优先 GnssPVTSolnMsg，其次 NavSatFix）---
        gnss_ok = False
        for cfg in self.gnss_topics:
            topic = cfg['topic']
            msg_type = cfg['type']
            try:
                if msg_type == 'GnssPVTSolnMsg':
                    _gnss_cb = partial(_handle_gnss_pvt, self._update_data, topic)
                    self.rosbridge.subscribe(topic, 'gnss_comm/GnssPVTSolnMsg', _gnss_cb)
                else:
                    _navsat_cb = partial(_handle_navsatfix, self._update_data, topic)
                    self.rosbridge.subscribe(topic, 'sensor_msgs/NavSatFix', _navsat_cb)
                self.subscribers[topic] = {'topic': topic, 'type': 'gnss', 'active': True}
                subscribed += 1
                gnss_ok = True
                logger.info(f"  GNSS 订阅成功: {topic} ({msg_type})")
                break
            except Exception as e:
                logger.warning(f"  GNSS 订阅失败 {topic}: {e}")
                continue

        if not gnss_ok:
            logger.warning("  所有 GNSS 话题订阅失败，将使用虚拟数据")

        # --- SLAM ---
        # Path
        path_topic = self.slam_topics['path']
        def _path_cb(data):
            _handle_path(self._update_data, path_topic, data)
        try:
            self.rosbridge.subscribe(path_topic, 'nav_msgs/Path', _path_cb)
            self.subscribers[path_topic] = {'topic': path_topic, 'type': 'path', 'active': True}
            subscribed += 1
            logger.info(f"  Path 订阅成功: {path_topic}")
        except Exception as e:
            logger.warning(f"  Path 订阅失败 {path_topic}: {e}")

        # Odometry
        odom_topic = self.slam_topics['odometry']
        def _odom_cb(data):
            _handle_odometry(self._update_data, odom_topic, data)
        try:
            self.rosbridge.subscribe(odom_topic, 'nav_msgs/Odometry', _odom_cb)
            self.subscribers[odom_topic] = {'topic': odom_topic, 'type': 'odometry', 'active': True}
            subscribed += 1
            logger.info(f"  Odometry 订阅成功: {odom_topic}")
        except Exception as e:
            logger.warning(f"  Odometry 订阅失败 {odom_topic}: {e}")

        # Registered Cloud
        cloud_topic = self.slam_topics['registered_cloud']
        def _cloud_cb(data):
            _handle_registered_cloud(self._update_data, cloud_topic, data)
        try:
            self.rosbridge.subscribe(cloud_topic, 'sensor_msgs/PointCloud2', _cloud_cb)
            self.subscribers[cloud_topic] = {'topic': cloud_topic, 'type': 'cloud', 'active': True}
            subscribed += 1
            logger.info(f"  RegisteredCloud 订阅成功: {cloud_topic}")
        except Exception as e:
            logger.warning(f"  RegisteredCloud 订阅失败 {cloud_topic}: {e}")

        logger.info(f"订阅器设置完毕: {subscribed}/{len(self.subscribers)} 个活跃")

    def _update_data(self, topic: str, data: Dict[str, Any], robot_id: str = '_direct'):
        """线程安全地更新最新数据。robot_id='_direct' 为 rosbridge 直连模式。
        保留 data 内的原始传感器时间戳不变，附加 _received_at 记录服务器接收时间。"""
        with self._lock:
            if robot_id not in self.robot_data:
                self.robot_data[robot_id] = {}
            self.robot_data[robot_id][topic] = {
                'timestamp': time.time(),
                'data': {**data, '_received_at': time.time()},
                'updated_at': time.time(),
            }
        logger.debug(f"数据更新: [{robot_id}] {topic}")

    def _robot_topic(self, topic: str, robot_id: str = None) -> Optional[Dict]:
        """获取指定机器人 + 话题的数据，robot_id 为 None 返回第一个匹配的。"""
        with self._lock:
            if robot_id and robot_id in self.robot_data:
                return self.robot_data[robot_id].get(topic)
            if robot_id is None:
                for rid in self.robot_data:
                    if topic in self.robot_data[rid]:
                        return self.robot_data[rid][topic]
        return None

    # ------------------------------------------------------------------
    # 数据获取方法（供 background_broadcast 调用）
    # ------------------------------------------------------------------

    async def get_latest_camera_data(self, robot_id: str = None) -> Optional[Dict[str, Any]]:
        camera_data = {}
        
        for topic in self.camera_topics:
            entry = self._robot_topic(topic, robot_id)
            if entry and 'data' in entry:
                d = entry['data']
                camera_id = d.get('camera_id', topic.split('/')[-2])
                camera_data[camera_id] = d

        # fallback: 扫描所有机器人数据中的相机条目
        if not camera_data:
            with self._lock:
                for rid in (robot_id and [robot_id] or self.robot_data):
                    for topic, entry in self.robot_data.get(rid, {}).items():
                        d = entry.get('data', {})
                        if isinstance(d, dict) and 'camera_id' in d and 'data' in d:
                            camera_data[d['camera_id']] = d

        return camera_data if camera_data else None

    async def get_latest_lidar_data(self, robot_id: str = None) -> Optional[Dict[str, Any]]:
        for topic in self.lidar_topics:
            entry = self._robot_topic(topic, robot_id)
            if entry and 'data' in entry:
                return entry['data']
        return None  # 无真实 LiDAR 数据时不返回假数据

    async def get_latest_imu_data(self, robot_id: str = None) -> Optional[Dict[str, Any]]:
        for topic in self.imu_topics:
            entry = self._robot_topic(topic, robot_id)
            if entry and 'data' in entry:
                return entry['data']
        return None  # 无真实 IMU 数据时不返回假数据

    async def get_latest_gnss_data(self, robot_id: str = None) -> Optional[Dict[str, Any]]:
        for cfg in self.gnss_topics:
            entry = self._robot_topic(cfg['topic'], robot_id)
            if entry and 'data' in entry:
                return entry['data']
        return None  # 无真实 GNSS 数据时不返回测试假数据

    async def get_latest_slam_data(self, robot_id: str = None) -> Optional[Dict[str, Any]]:
        slam_data = {}
        for key in ('path', 'odometry', 'registered_cloud'):
            topic = self.slam_topics[key]
            entry = self._robot_topic(topic, robot_id)
            if entry and 'data' in entry:
                slam_data[key] = entry['data']
        return slam_data if slam_data else None

    # ------------------------------------------------------------------
    # 多机器人查询接口
    # ------------------------------------------------------------------

    def get_robot_list(self) -> list:
        """返回所有在线机器人 ID 列表。"""
        with self._lock:
            return [rid for rid in self.robot_data if rid != '_direct']

    def get_robot_data(self, robot_id: str) -> Dict[str, Any]:
        """返回指定机器人的全部最新数据。"""
        with self._lock:
            return dict(self.robot_data.get(robot_id, {}))

    # ------------------------------------------------------------------
    # 连接状态
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        return self._running and self._initialized and (self.rosbridge.is_connected or len(self.robot_data) > 0)

    def get_connection_info(self) -> Dict[str, Any]:
        robot_ids = self.get_robot_list()
        return {
            'running': self._running,
            'initialized': self._initialized,
            'rosbridge_connected': self.rosbridge.is_connected,
            'subscriber_count': len(self.subscribers),
            'robot_count': len(robot_ids),
            'robot_ids': robot_ids,
            'subscribed_topics': self.rosbridge.get_subscribed_topics(),
            'subscriber_status': self.get_subscriber_status(),
        }

    def get_subscriber_status(self) -> Dict[str, Any]:
        status = {}
        for topic, sub in self.subscribers.items():
            status[topic] = sub if isinstance(sub, dict) else sub.get_status() if hasattr(sub, 'get_status') else {'topic': topic}
        return status

    def update_camera_settings(self, camera_id: str, preview_height=None, jpeg_quality=None):
        for topic, handler in self.subscribers.items():
            if hasattr(handler, 'camera_id') and handler.camera_id == camera_id:
                if hasattr(handler, 'update_settings'):
                    handler.update_settings(preview_height, jpeg_quality)
                    return True
        return False

    async def shutdown(self):
        self._running = False
        self.rosbridge.close()
        self.subscribers.clear()
        with self._lock:
            self.robot_data.clear()
        logger.info("ROSNodeManager 已关闭")

    # ------------------------------------------------------------------
    # 虚拟测试数据
