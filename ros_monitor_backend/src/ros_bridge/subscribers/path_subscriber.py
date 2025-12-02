"""
Path话题订阅器
订阅nav_msgs/Path消息，用于显示机器人运动轨迹
"""
from typing import Callable, Dict, Any, List
import logging
import time

try:
    import rospy
    from nav_msgs.msg import Path
except Exception:
    rospy = None
    Path = None

logger = logging.getLogger(__name__)


class PathSubscriber:
    """Path话题订阅器 - 用于轨迹可视化"""
    
    def __init__(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        self._topic = topic
        self._callback = callback
        self._sub = None
        self._last_update = 0
        self._message_count = 0
        self._max_points = 1000  # 最大保留点数，避免数据过大
        
        if rospy is None or Path is None:
            logger.warning(f"ROS not available, PathSubscriber for {topic} not created")
            return
            
        try:
            self._sub = rospy.Subscriber(
                topic, 
                Path, 
                self._on_message, 
                queue_size=1
            )
            logger.info(f"PathSubscriber created for topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to create PathSubscriber for {topic}: {e}")
    
    def _on_message(self, msg: 'Path') -> None:
        """处理接收到的Path消息"""
        try:
            self._message_count += 1
            self._last_update = time.time()
            
            # 提取路径点数据
            poses = []
            total_poses = len(msg.poses)
            
            # 如果点太多，进行降采样
            if total_poses > self._max_points:
                step = total_poses // self._max_points
                indices = range(0, total_poses, step)
            else:
                indices = range(total_poses)
            
            for i in indices:
                pose = msg.poses[i]
                poses.append({
                    'position': {
                        'x': float(pose.pose.position.x),
                        'y': float(pose.pose.position.y),
                        'z': float(pose.pose.position.z)
                    },
                    'orientation': {
                        'x': float(pose.pose.orientation.x),
                        'y': float(pose.pose.orientation.y),
                        'z': float(pose.pose.orientation.z),
                        'w': float(pose.pose.orientation.w)
                    }
                })
            
            payload = {
                'topic': self._topic,
                'timestamp': msg.header.stamp.to_sec(),
                'frame_id': msg.header.frame_id,
                'sequence': msg.header.seq,
                'total_poses': total_poses,
                'sampled_poses': len(poses),
                'poses': poses
            }
            
            self._callback(payload)
            
        except Exception as e:
            logger.error(f"Error processing Path message: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取订阅器状态"""
        return {
            'topic': self._topic,
            'type': 'nav_msgs/Path',
            'active': self._sub is not None,
            'message_count': self._message_count,
            'last_update': self._last_update
        }
    
    def shutdown(self):
        """关闭订阅器"""
        if self._sub:
            try:
                self._sub.unregister()
                logger.info(f"PathSubscriber for {self._topic} shutdown")
            except Exception as e:
                logger.error(f"Error shutting down PathSubscriber: {e}")

