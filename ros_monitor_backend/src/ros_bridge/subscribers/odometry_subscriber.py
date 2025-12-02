"""
Odometry话题订阅器
订阅nav_msgs/Odometry消息，用于显示当前机器人位姿
"""
from typing import Callable, Dict, Any
import logging
import time

try:
    import rospy
    from nav_msgs.msg import Odometry
except Exception:
    rospy = None
    Odometry = None

logger = logging.getLogger(__name__)


class OdometrySubscriber:
    """Odometry话题订阅器 - 用于实时位姿显示"""
    
    def __init__(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        self._topic = topic
        self._callback = callback
        self._sub = None
        self._last_update = 0
        self._message_count = 0
        
        if rospy is None or Odometry is None:
            logger.warning(f"ROS not available, OdometrySubscriber for {topic} not created")
            return
            
        try:
            self._sub = rospy.Subscriber(
                topic, 
                Odometry, 
                self._on_message, 
                queue_size=1
            )
            logger.info(f"OdometrySubscriber created for topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to create OdometrySubscriber for {topic}: {e}")
    
    def _on_message(self, msg: 'Odometry') -> None:
        """处理接收到的Odometry消息"""
        try:
            self._message_count += 1
            self._last_update = time.time()
            
            payload = {
                'topic': self._topic,
                'timestamp': msg.header.stamp.to_sec(),
                'frame_id': msg.header.frame_id,
                'child_frame_id': msg.child_frame_id,
                'sequence': msg.header.seq,
                'pose': {
                    'position': {
                        'x': float(msg.pose.pose.position.x),
                        'y': float(msg.pose.pose.position.y),
                        'z': float(msg.pose.pose.position.z)
                    },
                    'orientation': {
                        'x': float(msg.pose.pose.orientation.x),
                        'y': float(msg.pose.pose.orientation.y),
                        'z': float(msg.pose.pose.orientation.z),
                        'w': float(msg.pose.pose.orientation.w)
                    }
                },
                'twist': {
                    'linear': {
                        'x': float(msg.twist.twist.linear.x),
                        'y': float(msg.twist.twist.linear.y),
                        'z': float(msg.twist.twist.linear.z)
                    },
                    'angular': {
                        'x': float(msg.twist.twist.angular.x),
                        'y': float(msg.twist.twist.angular.y),
                        'z': float(msg.twist.twist.angular.z)
                    }
                }
            }
            
            self._callback(payload)
            
        except Exception as e:
            logger.error(f"Error processing Odometry message: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取订阅器状态"""
        return {
            'topic': self._topic,
            'type': 'nav_msgs/Odometry',
            'active': self._sub is not None,
            'message_count': self._message_count,
            'last_update': self._last_update
        }
    
    def shutdown(self):
        """关闭订阅器"""
        if self._sub:
            try:
                self._sub.unregister()
                logger.info(f"OdometrySubscriber for {self._topic} shutdown")
            except Exception as e:
                logger.error(f"Error shutting down OdometrySubscriber: {e}")

