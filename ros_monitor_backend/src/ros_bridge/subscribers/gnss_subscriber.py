#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNSS/RTK数据订阅器
订阅gnss_comm/GnssPVTSolnMsg消息,提取关键定位信息
"""

import rospy
from typing import Callable, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)

# 尝试导入gnss_comm消息,如果失败则记录警告
try:
    from gnss_comm.msg import GnssPVTSolnMsg
    GNSS_COMM_AVAILABLE = True
except ImportError:
    logger.warning("gnss_comm包未安装,GNSS订阅器将不可用")
    logger.warning("安装方法: sudo apt-get install ros-noetic-gnss-comm")
    GNSS_COMM_AVAILABLE = False
    GnssPVTSolnMsg = None  # 占位符

class GNSSSubscriber:
    """GNSS/RTK数据订阅器"""
    
    def __init__(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        """
        初始化GNSS订阅器
        
        Args:
            topic: GNSS话题路径
            callback: 数据回调函数
        """
        self.topic = topic
        self.callback = callback
        self.subscriber = None
        self.frame_count = 0
        self.last_frame_time = 0
        self.is_active = False
        
        logger.info(f"创建GNSS订阅器: topic={topic}")
        self._setup_subscriber()
    
    def _setup_subscriber(self):
        """设置ROS订阅器"""
        if not GNSS_COMM_AVAILABLE:
            logger.error(f"无法创建GNSS订阅器: gnss_comm包未安装")
            self.is_active = False
            return
            
        try:
            self.subscriber = rospy.Subscriber(
                self.topic,
                GnssPVTSolnMsg,
                self._gnss_callback,
                queue_size=10
            )
            self.is_active = True
            logger.info(f"GNSS订阅器创建成功: {self.topic}")
        except Exception as e:
            logger.error(f"创建GNSS订阅器失败 {self.topic}: {e}")
            self.is_active = False
    
    def _gnss_callback(self, msg: GnssPVTSolnMsg):
        """
        GNSS消息回调函数
        
        Args:
            msg: GnssPVTSolnMsg消息
        """
        try:
            current_time = time.time()
            
            # 解析RTK状态
            rtk_status = self._get_rtk_status(msg)
            
            # 提取定位质量信息
            quality = self._get_quality_info(msg)
            
            # 提取位置信息(保留高精度)
            position = {
                'latitude': round(msg.latitude, 8),      # 8位小数约1mm精度
                'longitude': round(msg.longitude, 8),
                'altitude': round(msg.altitude, 3),      # 3位小数约1mm精度
                'height_msl': round(msg.height_msl, 3)   # 海拔高度
            }
            
            # 提取精度信息
            accuracy = {
                'h_acc': round(msg.h_acc, 4),    # 水平精度(米)
                'v_acc': round(msg.v_acc, 4),    # 垂直精度(米)
                'p_dop': round(msg.p_dop, 2)     # 位置精度因子
            }
            
            # 提取速度信息
            velocity = {
                'vel_n': round(msg.vel_n, 3),      # 北向速度(m/s)
                'vel_e': round(msg.vel_e, 3),      # 东向速度(m/s)
                'vel_d': round(msg.vel_d, 3),      # 下向速度(m/s)
                'vel_acc': round(msg.vel_acc, 3)   # 速度精度(m/s)
            }
            
            # 提取时间信息
            time_info = {
                'week': msg.time.week,    # GPS周数
                'tow': round(msg.time.tow, 1)  # 周内秒
            }
            
            # 组装完整数据
            gnss_data = {
                'rtk_status': rtk_status,
                'quality': quality,
                'position': position,
                'accuracy': accuracy,
                'velocity': velocity,
                'time': time_info,
                'timestamp': msg.header.stamp.to_sec() if hasattr(msg, 'header') else current_time,
                'sequence': self.frame_count
            }
            
            # 调用回调函数
            self.callback(gnss_data)
            
            self.frame_count += 1
            self.last_frame_time = current_time
            
            # 每100帧打印一次日志
            if self.frame_count % 100 == 0:
                logger.info(f"[{self.topic}] GNSS数据处理成功, 帧数: {self.frame_count}, RTK状态: {rtk_status}")
            
        except Exception as e:
            logger.error(f"[{self.topic}] GNSS回调错误: {e}")
            import traceback
            logger.error(f"[{self.topic}] 错误详情: {traceback.format_exc()}")
    
    def _get_rtk_status(self, msg: GnssPVTSolnMsg) -> str:
        """
        解析RTK状态
        
        Args:
            msg: GNSS消息
            
        Returns:
            RTK状态字符串
        """
        # carr_soln: 载波解状态
        # 0 = 无载波解
        # 1 = 浮点解
        # 2 = 固定解
        if msg.carr_soln == 2:
            return 'RTK_FIXED'      # ✅ RTK固定解
        elif msg.carr_soln == 1:
            return 'RTK_FLOAT'      # ⚠️ RTK浮点解
        elif msg.fix_type == 3:
            return 'GPS_3D'         # 📡 3D定位
        elif msg.fix_type == 2:
            return 'GPS_2D'         # 📡 2D定位
        elif msg.fix_type == 1:
            return 'GPS_1D'         # 单点定位
        else:
            return 'NO_FIX'         # ❌ 无定位
    
    def _get_quality_info(self, msg: GnssPVTSolnMsg) -> Dict[str, Any]:
        """
        获取定位质量信息
        
        Args:
            msg: GNSS消息
            
        Returns:
            质量信息字典
        """
        return {
            'fix_type': msg.fix_type,          # 定位类型: 0=无, 1=单点, 2=2D, 3=3D
            'valid_fix': msg.valid_fix,        # 定位有效性
            'diff_soln': msg.diff_soln,        # 是否应用差分改正
            'carr_soln': msg.carr_soln,        # 载波解状态: 0=无, 1=浮点, 2=固定
            'num_sv': msg.num_sv               # 使用的卫星数量
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取订阅器状态
        
        Returns:
            状态信息字典
        """
        return {
            'topic': self.topic,
            'is_active': self.is_active,
            'frame_count': self.frame_count,
            'last_frame_time': self.last_frame_time
        }
    
    def shutdown(self):
        """关闭订阅器"""
        try:
            if self.subscriber:
                self.subscriber.unregister()
                self.subscriber = None
            self.is_active = False
            logger.info(f"GNSS订阅器关闭: {self.topic}")
        except Exception as e:
            logger.error(f"关闭GNSS订阅器时发生错误 {self.topic}: {e}")
