"""
Registered Point Cloud订阅器
订阅/cloud_registered话题，用于显示当前帧配准后的点云
支持降采样以提高传输效率
"""
from typing import Callable, Dict, Any, List
import logging
import time
import random

try:
    import rospy
    from sensor_msgs.msg import PointCloud2
    import sensor_msgs.point_cloud2 as pc2
except Exception:
    rospy = None
    PointCloud2 = None
    pc2 = None

logger = logging.getLogger(__name__)


class RegisteredCloudSubscriber:
    """配准点云订阅器 - 用于SLAM地图可视化"""
    
    def __init__(self, topic: str, callback: Callable[[Dict[str, Any]], None], 
                 max_points: int = 5000, voxel_size: float = 0.1):
        self._topic = topic
        self._callback = callback
        self._sub = None
        self._last_update = 0
        self._message_count = 0
        self._max_points = max_points  # 最大点数
        self._voxel_size = voxel_size  # 体素大小用于降采样
        
        if rospy is None or PointCloud2 is None:
            logger.warning(f"ROS not available, RegisteredCloudSubscriber for {topic} not created")
            return
            
        try:
            self._sub = rospy.Subscriber(
                topic, 
                PointCloud2, 
                self._on_message, 
                queue_size=1
            )
            logger.info(f"RegisteredCloudSubscriber created for topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to create RegisteredCloudSubscriber for {topic}: {e}")
    
    def _on_message(self, msg: 'PointCloud2') -> None:
        """处理接收到的PointCloud2消息"""
        import struct

        try:
            self._message_count += 1
            self._last_update = time.time()

            # 检查是否包含RGB字段
            field_names = [f.name for f in msg.fields]
            has_rgb = 'rgb' in field_names

            # 读取点云数据
            points = []
            colors = []  # RGB颜色数组 [r, g, b] 每个值0-255
            total_points = 0

            # 确定要读取的字段
            if has_rgb:
                read_fields = ("x", "y", "z", "rgb")
            else:
                read_fields = ("x", "y", "z")

            # 先统计总点数
            for p in pc2.read_points(msg, field_names=read_fields, skip_nans=True):
                total_points += 1

            # 随机采样以限制点数
            if total_points > self._max_points:
                sample_ratio = self._max_points / total_points
            else:
                sample_ratio = 1.0

            for p in pc2.read_points(msg, field_names=read_fields, skip_nans=True):
                if sample_ratio < 1.0 and random.random() > sample_ratio:
                    continue
                if len(points) >= self._max_points:
                    break
                points.append([float(p[0]), float(p[1]), float(p[2])])

                # 提取RGB颜色
                if has_rgb:
                    # ROS中rgb是packed float, 需要解码为BGR
                    rgb_float = p[3]
                    # 将float转为int32位
                    rgb_int = struct.unpack('I', struct.pack('f', rgb_float))[0]
                    # 提取BGR (ROS使用BGR顺序)
                    b = (rgb_int >> 0) & 0xFF
                    g = (rgb_int >> 8) & 0xFF
                    r = (rgb_int >> 16) & 0xFF
                    colors.append([r, g, b])
                else:
                    # 默认白色
                    colors.append([255, 255, 255])

            payload = {
                'topic': self._topic,
                'timestamp': msg.header.stamp.to_sec(),
                'frame_id': msg.header.frame_id,
                'sequence': msg.header.seq,
                'total_points': total_points,
                'sampled_points': len(points),
                'points': points,
                'colors': colors,  # 添加颜色数组
                'has_rgb': has_rgb,
                'fields': ['x', 'y', 'z', 'rgb'] if has_rgb else ['x', 'y', 'z']
            }

            self._callback(payload)

        except Exception as e:
            logger.error(f"Error processing PointCloud2 message: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def update_settings(self, max_points: int = None, voxel_size: float = None):
        """更新采样设置"""
        if max_points is not None:
            self._max_points = max_points
        if voxel_size is not None:
            self._voxel_size = voxel_size
        logger.info(f"Updated settings: max_points={self._max_points}, voxel_size={self._voxel_size}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取订阅器状态"""
        return {
            'topic': self._topic,
            'type': 'sensor_msgs/PointCloud2',
            'active': self._sub is not None,
            'message_count': self._message_count,
            'last_update': self._last_update,
            'max_points': self._max_points
        }
    
    def shutdown(self):
        """关闭订阅器"""
        if self._sub:
            try:
                self._sub.unregister()
                logger.info(f"RegisteredCloudSubscriber for {self._topic} shutdown")
            except Exception as e:
                logger.error(f"Error shutting down RegisteredCloudSubscriber: {e}")

