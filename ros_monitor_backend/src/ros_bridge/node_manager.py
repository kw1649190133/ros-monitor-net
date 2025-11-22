import asyncio
import rospy
from threading import Thread
from typing import Dict, Any, Optional, List
import json
import logging
import time

from src.ros_bridge.subscribers.compressed_camera_subscriber import CompressedCameraSubscriber
from src.ros_bridge.subscribers.lidar_subscriber import LidarSubscriber
from src.ros_bridge.subscribers.imu_subscriber import ImuSubscriber
from src.ros_bridge.subscribers.gnss_subscriber import GNSSSubscriber
from src.ros_bridge.subscribers.navsatfix_subscriber import NavSatFixSubscriber
from src.utils.camera_config_loader import camera_config

logger = logging.getLogger(__name__)

class ROSNodeManager:
    """ROS节点管理器，负责管理所有ROS相关的订阅和发布"""
    
    def __init__(self):
        self.ros_thread: Optional[Thread] = None
        self.subscribers: Dict[str, Any] = {}
        self.latest_data: Dict[str, Any] = {}
        self._running = False
        self._initialized = False
        
        # 从配置文件加载相机话题
        self.camera_topics = camera_config.get_topic_list()
        logger.info(f"从配置文件加载相机话题: {self.camera_topics}")
        
        # 加载图像处理参数
        self.image_params = camera_config.get_image_processing_params()
        logger.info(f"图像处理参数: {self.image_params}")
        
        self.lidar_topics = [
            '/livox/lidar'
        ]
        self.imu_topics = [
            '/livox/imu'
        ]
        self.gnss_topics = [
            # 优先使用GnssPVTSolnMsg话题(信息全面,包含RTK状态、卫星数、速度等)
            {'topic': '/ublox_driver/receiver_pvt', 'type': 'GnssPVTSolnMsg'},
            # 备用NavSatFix话题(标准ROS消息,但信息缺失严重)
            {'topic': '/ublox_driver/receiver_lla', 'type': 'NavSatFix'}
        ]
        
    async def initialize(self):
        """初始化ROS节点"""
        try:
            logger.info("开始初始化ROS节点管理器...")
            
            # 在单独线程中初始化ROS
            self.ros_thread = Thread(target=self._init_ros_node, daemon=True)
            self.ros_thread.start()
            logger.info("ROS初始化线程已启动")
            
            # 等待ROS初始化完成
            logger.info("等待ROS初始化完成...")
            await asyncio.sleep(2.0)
            
            # 检查ROS节点状态
            logger.info(f"检查ROS节点状态: rospy.is_shutdown() = {rospy.is_shutdown()}")
            
            if not rospy.is_shutdown():
                logger.info("ROS节点初始化成功，开始设置订阅器...")
                self._setup_subscribers()
                self._running = True
                self._initialized = True
                logger.info("ROS节点管理器初始化成功")
            else:
                logger.error("ROS节点初始化失败: rospy.is_shutdown() 返回 True")
                raise Exception("Failed to initialize ROS node")
                
        except Exception as e:
            logger.error(f"ROS初始化失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
            
    def _init_ros_node(self):
        """在单独线程中初始化ROS节点"""
        try:
            logger.info("开始初始化ROS节点...")
            rospy.init_node('ros_monitor_bridge', anonymous=True, disable_signals=True)
            logger.info("ROS节点 'ros_monitor_bridge' 初始化成功")
            logger.info(f"节点名称: {rospy.get_name()}")
            logger.info(f"是否关闭: {rospy.is_shutdown()}")
        except Exception as e:
            logger.error(f"ROS节点初始化失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            
    def _setup_subscribers(self):
        """设置ROS话题订阅器"""
        try:
            # 设置相机订阅器 - 使用配置文件中的话题
            for topic in self.camera_topics:
                try:
                    # 从配置获取相机ID
                    camera_id = camera_config.get_camera_id_by_topic(topic)
                    
                    subscriber = CompressedCameraSubscriber(
                        topic=topic,
                        camera_id=camera_id,  # 传递配置的camera_id
                        callback=lambda data, t=topic: self._update_data(t, data),
                        image_params=self.image_params  # 传递图像处理参数
                    )
                    self.subscribers[topic] = subscriber
                    logger.info(f"Compressed camera subscriber created for {topic} (camera_id: {camera_id})")
                except Exception as e:
                    logger.warning(f"Failed to create compressed camera subscriber for {topic}: {e}")
            
            # 设置激光雷达订阅器
            for topic in self.lidar_topics:
                try:
                    subscriber = LidarSubscriber(
                        topic=topic,
                        callback=lambda data, t=topic: self._update_data(t, data)
                    )
                    self.subscribers[topic] = subscriber
                    logger.info(f"Lidar subscriber created for {topic}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to create lidar subscriber for {topic}: {e}")
            
            # 设置IMU订阅器
            for topic in self.imu_topics:
                try:
                    subscriber = ImuSubscriber(
                        topic=topic,
                        callback=lambda data, t=topic: self._update_data(t, data)
                    )
                    self.subscribers[topic] = subscriber
                    logger.info(f"IMU subscriber created for {topic}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to create IMU subscriber for {topic}: {e}")
            
            # 设置GNSS订阅器 - 自动选择NavSatFix或GnssPVTSolnMsg
            gnss_created = False
            for gnss_config in self.gnss_topics:
                topic = gnss_config['topic']
                msg_type = gnss_config['type']
                logger.info(f"🔍 尝试创建GNSS订阅器: {topic} ({msg_type})")
                try:
                    if msg_type == 'NavSatFix':
                        # 使用NavSatFix订阅器(推荐)
                        subscriber = NavSatFixSubscriber(
                            topic=topic,
                            callback=lambda data, t=topic: self._update_data(t, data)
                        )
                        self.subscribers[topic] = subscriber
                        logger.info(f"✅ NavSatFix GNSS订阅器创建成功: {topic}")
                        gnss_created = True
                        break  # 成功后停止尝试
                    else:
                        # 备用: 使用GnssPVTSolnMsg订阅器
                        subscriber = GNSSSubscriber(
                            topic=topic,
                            callback=lambda data, t=topic: self._update_data(t, data)
                        )
                        self.subscribers[topic] = subscriber
                        logger.info(f"✅ GnssPVTSolnMsg GNSS订阅器创建成功: {topic}")
                        gnss_created = True
                        break
                except Exception as e:
                    logger.warning(f"❌ 创建GNSS订阅器失败 {topic} ({msg_type}): {e}")
                    import traceback
                    logger.debug(f"错误堆栈: {traceback.format_exc()}")
                    continue  # 尝试下一个
            
            if not gnss_created:
                logger.error("⚠️ 所有GNSS订阅器创建失败，将使用虚拟数据")
            
            logger.info(f"ROS subscribers setup completed. Total: {len(self.subscribers)}")
            
        except Exception as e:
            logger.error(f"Failed to setup ROS subscribers: {e}")
            
    def _update_data(self, topic: str, data: Dict[str, Any]):
        """更新最新数据"""
        try:
            self.latest_data[topic] = {
                'timestamp': rospy.get_time() if not rospy.is_shutdown() else time.time(),
                'data': data,
                'updated_at': time.time()
            }
            # 对GNSS数据进行特别日志
            if 'gnss' in topic.lower() or 'receiver' in topic.lower():
                rtk_status = data.get('rtk_status', 'UNKNOWN')
                logger.info(f"📡 GNSS数据更新成功: {topic}, RTK={rtk_status}, 帧数={data.get('sequence', 0)}")
            else:
                logger.debug(f"数据更新成功: {topic}, 帧数: {data.get('sequence', 0)}")
        except Exception as e:
            logger.error(f"Error updating data for topic {topic}: {e}")
        
    async def get_latest_camera_data(self) -> Optional[Dict[str, Any]]:
        """获取最新相机数据"""
        camera_data = {}
        
        for topic in self.camera_topics:
            if topic in self.latest_data:
                data = self.latest_data[topic]
                if data and 'data' in data:
                    camera_id = data['data'].get('camera_id', topic.split('/')[-2])
                    camera_data[camera_id] = data['data']
                    logger.info(f"获取相机数据: {camera_id}, 帧数: {data['data'].get('sequence', 0)}")
        
        # 如果没有真实数据，返回测试数据
        if not camera_data:
            logger.warning("没有真实相机数据，返回测试数据")
            camera_data = await self._get_test_camera_data()
        
        return camera_data if camera_data else None
    
    async def _get_test_camera_data(self) -> Dict[str, Any]:
        """生成测试相机数据"""
        if not hasattr(self, '_test_camera_counter'):
            self._test_camera_counter = 0
        
        self._test_camera_counter += 1
        
        try:
            import cv2
            import numpy as np
            import base64
            
            # 创建测试图像
            img = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(img, f'Test Camera {self._test_camera_counter}', (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(img, f'Time: {time.strftime("%H:%M:%S")}', (10, 150), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # 编码为JPEG
            _, jpeg_data = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            image_base64 = base64.b64encode(jpeg_data).decode('utf-8')
            
            return {
                'left_camera': {
                    'camera_id': 'left_camera',
                    'topic': '/left_camera/image/compressed',
                    'timestamp': time.time(),
                    'sequence': self._test_camera_counter,
                    'encoding': 'jpeg',
                    'width': 320,
                    'height': 240,
                    'data': image_base64,
                    'compressed': True,
                    'compressed_size': len(jpeg_data),
                    'compression_ratio': 15.0,
                    'frame_rate': 10.0
                },
                'right_camera': {
                    'camera_id': 'right_camera',
                    'topic': '/right_camera/image/compressed',
                    'timestamp': time.time(),
                    'sequence': self._test_camera_counter,
                    'encoding': 'jpeg',
                    'width': 320,
                    'height': 240,
                    'data': image_base64,
                    'compressed': True,
                    'compressed_size': len(jpeg_data),
                    'compression_ratio': 15.0,
                    'frame_rate': 10.0
                }
            }
        except ImportError:
            logger.warning("OpenCV not available, using placeholder camera data")
            return {
                'left_camera': {
                    'camera_id': 'left_camera',
                    'timestamp': time.time(),
                    'sequence': self._test_camera_counter,
                    'encoding': 'jpeg',
                    'width': 320,
                    'height': 240,
                    'data': 'data:image/jpeg;base64,',  # 占位符
                    'compressed': True,
                    'compressed_size': 0,
                    'compression_ratio': 0.0,
                    'frame_rate': 0.0
                }
            }
        
    async def get_latest_lidar_data(self) -> Optional[Dict[str, Any]]:
        """获取最新激光雷达数据"""
        # 模拟激光雷达数据
        return {
            'timestamp': rospy.get_time() if not rospy.is_shutdown() else 0,
            'point_count': 1000,
            'data': [0.1, 0.2, 0.3] * 1000,  # 简化的点云数据
            'fields': ['x', 'y', 'z']
        }
        
    async def get_latest_imu_data(self) -> Optional[Dict[str, Any]]:
        """获取最新IMU数据"""
        # 模拟IMU数据
        return {
            'timestamp': rospy.get_time() if not rospy.is_shutdown() else 0,
            'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0},
            'angular_velocity': {'x': 0.1, 'y': 0.2, 'z': 0.3},
            'linear_acceleration': {'x': 9.8, 'y': 0.0, 'z': 0.0}
        }
    
    async def get_latest_gnss_data(self) -> Optional[Dict[str, Any]]:
        """获取最新GNSS数据"""
        # 检查所有可能的GNSS话题
        for gnss_config in self.gnss_topics:
            topic = gnss_config['topic']
            if topic in self.latest_data:
                data = self.latest_data[topic]
                if data and 'data' in data:
                    logger.info(f"📡 返回GNSS真实数据: {topic}")
                    return data['data']
        
        # 如果没有真实数据,返回虚拟数据便于测试
        logger.warning("⚠️  没有真实GNSS数据,返回虚拟数据")
        return await self._get_test_gnss_data()
    
    async def _get_test_gnss_data(self) -> Dict[str, Any]:
        """生成虚拟GNSS测试数据"""
        if not hasattr(self, '_test_gnss_counter'):
            self._test_gnss_counter = 0
        
        self._test_gnss_counter += 1
        
        import random
        import math
        
        # 模拟北京附近的GPS坐标，带微小随机漂移
        base_lat = 39.0790108
        base_lon = 117.7151327
        base_alt = -2.5
        
        # 添加微小随机漂移(模拟移动)
        drift = 0.00001  # 约1米的漂移
        lat = base_lat + random.uniform(-drift, drift)
        lon = base_lon + random.uniform(-drift, drift)
        alt = base_alt + random.uniform(-0.1, 0.1)
        
        # 模拟RTK状态循环: RTK_FIXED -> RTK_FLOAT -> GPS_3D
        status_cycle = ['RTK_FIXED', 'RTK_FLOAT', 'GPS_3D']
        rtk_status = status_cycle[self._test_gnss_counter % 3]
        
        # 根据状态设置精度
        if rtk_status == 'RTK_FIXED':
            h_acc = random.uniform(0.01, 0.03)  # 1-3cm
            v_acc = random.uniform(0.02, 0.04)
            num_sv = random.randint(20, 28)
            carr_soln = 2
        elif rtk_status == 'RTK_FLOAT':
            h_acc = random.uniform(0.1, 0.3)  # 10-30cm
            v_acc = random.uniform(0.15, 0.35)
            num_sv = random.randint(15, 22)
            carr_soln = 1
        else:  # GPS_3D
            h_acc = random.uniform(1.0, 3.0)  # 1-3m
            v_acc = random.uniform(1.5, 4.0)
            num_sv = random.randint(8, 15)
            carr_soln = 0
        
        return {
            'rtk_status': rtk_status,
            'quality': {
                'fix_type': 3,
                'valid_fix': True,
                'diff_soln': rtk_status in ['RTK_FIXED', 'RTK_FLOAT'],
                'carr_soln': carr_soln,
                'num_sv': num_sv
            },
            'position': {
                'latitude': round(lat, 8),
                'longitude': round(lon, 8),
                'altitude': round(alt, 3),
                'height_msl': round(alt + 7.0, 3)  # 模拟MSL高度
            },
            'accuracy': {
                'h_acc': round(h_acc, 4),
                'v_acc': round(v_acc, 4),
                'p_dop': round(math.sqrt(h_acc**2 + v_acc**2) / 2, 2)
            },
            'velocity': {
                'vel_n': round(random.uniform(-0.5, 0.5), 3),
                'vel_e': round(random.uniform(-0.5, 0.5), 3),
                'vel_d': round(random.uniform(-0.1, 0.1), 3),
                'vel_acc': round(random.uniform(0.1, 0.3), 3)
            },
            'time': {
                'week': 2393,
                'tow': time.time() % 604800  # GPS周内秒
            },
            'timestamp': time.time(),
            'sequence': self._test_gnss_counter
        }
        
    def is_connected(self) -> bool:
        """检查ROS连接状态"""
        return self._running and self._initialized and not rospy.is_shutdown()
        
    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            'running': self._running,
            'initialized': self._initialized,
            'ros_shutdown': rospy.is_shutdown(),
            'subscriber_count': len(self.subscribers),
            'data_topics': list(self.latest_data.keys()),
            'subscriber_status': self.get_subscriber_status()
        }
    
    def get_subscriber_status(self) -> Dict[str, Any]:
        """获取所有订阅器状态"""
        status = {}
        for topic, subscriber in self.subscribers.items():
            if hasattr(subscriber, 'get_status'):
                status[topic] = subscriber.get_status()
            else:
                status[topic] = {'topic': topic, 'status': 'unknown'}
        return status
    
    def update_camera_settings(self, camera_id: str, preview_height: int = None, jpeg_quality: int = None):
        """更新相机设置"""
        for topic, subscriber in self.subscribers.items():
            if hasattr(subscriber, 'camera_id') and subscriber.camera_id == camera_id:
                if hasattr(subscriber, 'update_settings'):
                    subscriber.update_settings(preview_height, jpeg_quality)
                    logger.info(f"Updated settings for camera {camera_id}")
                    return True
        logger.warning(f"Camera {camera_id} not found for settings update")
        return False
        
    async def shutdown(self):
        """关闭ROS节点管理器"""
        try:
            self._running = False
            
            # 关闭所有订阅器
            for topic, subscriber in self.subscribers.items():
                if hasattr(subscriber, 'shutdown'):
                    subscriber.shutdown()
            
            # 关闭ROS节点
            if not rospy.is_shutdown():
                rospy.signal_shutdown("Application shutdown")
            
            logger.info("ROS Node Manager shutdown completed")
        except Exception as e:
            logger.error(f"ROS shutdown error: {e}")