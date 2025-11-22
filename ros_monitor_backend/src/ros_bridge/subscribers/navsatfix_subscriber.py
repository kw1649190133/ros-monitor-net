#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NavSatFix GNSS数据订阅器
订阅sensor_msgs/NavSatFix消息,提取GNSS定位信息
这是ROS标准消息格式,不需要额外的gnss_comm依赖
"""

import rospy
from sensor_msgs.msg import NavSatFix
from typing import Callable, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)

class NavSatFixSubscriber:
    """NavSatFix GNSS数据订阅器"""
    
    def __init__(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        """
        初始化NavSatFix订阅器
        
        Args:
            topic: GNSS话题路径
            callback: 数据回调函数
        """
        self.topic = topic
        self.callback = callback
        self.subscriber = None
        self.is_active = False
        self.frame_count = 0
        self.last_frame_time = None
        
        self._setup_subscriber()
    
    def _setup_subscriber(self):
        """设置ROS订阅器"""
        try:
            self.subscriber = rospy.Subscriber(
                self.topic,
                NavSatFix,
                self._navsatfix_callback,
                queue_size=10
            )
            self.is_active = True
            logger.info(f"NavSatFix订阅器创建成功: {self.topic}")
        except Exception as e:
            logger.error(f"创建NavSatFix订阅器失败 {self.topic}: {e}")
            self.is_active = False
    
    def _navsatfix_callback(self, msg: NavSatFix):
        """
        处理NavSatFix消息
        
        Args:
            msg: NavSatFix消息对象
        """
        try:
            self.frame_count += 1
            self.last_frame_time = time.time()
            
            # 解析RTK状态
            rtk_status = self._get_rtk_status(msg)
            
            # 提取定位质量信息
            quality = self._get_quality_info(msg)
            
            # 提取位置信息(保留高精度)
            position = {
                'latitude': round(msg.latitude, 8),      # 8位小数约1mm精度
                'longitude': round(msg.longitude, 8),
                'altitude': round(msg.altitude, 3),      # 3位小数约1mm精度
                'height_msl': round(msg.altitude, 3)     # NavSatFix没有单独的MSL高度
            }
            
            # 提取精度信息
            accuracy = self._get_accuracy_info(msg)
            
            # NavSatFix不包含速度信息,设置为0
            velocity = {
                'vel_n': 0.0,
                'vel_e': 0.0,
                'vel_d': 0.0,
                'vel_acc': 0.0
            }
            
            # 提取时间信息
            time_info = {
                'week': 0,  # NavSatFix不包含GPS周数
                'tow': msg.header.stamp.to_sec()  # 使用ROS时间戳
            }
            
            # 组装完整数据
            gnss_data = {
                'rtk_status': rtk_status,
                'quality': quality,
                'position': position,
                'accuracy': accuracy,
                'velocity': velocity,
                'time': time_info,
                'timestamp': msg.header.stamp.to_sec(),
                'sequence': self.frame_count
            }
            
            # 调用回调函数
            self.callback(gnss_data)
            
            logger.debug(f"NavSatFix数据已处理: 帧#{self.frame_count}, RTK={rtk_status}")
            
        except Exception as e:
            logger.error(f"处理NavSatFix消息时发生错误 {self.topic}: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
    
    def _get_rtk_status(self, msg: NavSatFix) -> str:
        """
        解析RTK状态
        
        NavSatFix的status字段:
        -1 = 无定位 (STATUS_NO_FIX)
         0 = 单点定位 (STATUS_FIX)
         1 = SBAS差分 (STATUS_SBAS_FIX)
         2 = GBAS差分/RTK (STATUS_GBAS_FIX)
        
        Args:
            msg: NavSatFix消息
            
        Returns:
            RTK状态字符串
        """
        status = msg.status.status
        
        if status == 2:
            return 'RTK_FIXED'      # GBAS/RTK差分
        elif status == 1:
            return 'GPS_3D'         # SBAS差分(视为3D定位)
        elif status == 0:
            return 'GPS_3D'         # 单点3D定位
        else:
            return 'NO_FIX'         # 无定位
    
    def _get_quality_info(self, msg: NavSatFix) -> Dict[str, Any]:
        """
        获取定位质量信息
        
        Args:
            msg: NavSatFix消息
            
        Returns:
            质量信息字典
        """
        # NavSatFix的status字段映射到fix_type
        status = msg.status.status
        fix_type = 3 if status >= 0 else 0  # 0=无定位, 3=3D定位
        
        return {
            'fix_type': fix_type,
            'valid_fix': status >= 0,
            'diff_soln': status >= 1,  # SBAS或GBAS差分
            'carr_soln': 2 if status == 2 else 0,  # 2=RTK固定解, 0=其他
            'num_sv': 0  # NavSatFix不包含卫星数量,设为0
        }
    
    def _get_accuracy_info(self, msg: NavSatFix) -> Dict[str, Any]:
        """
        提取精度信息
        
        position_covariance是3x3矩阵(ENU坐标系):
        [E_var,  E_N,   E_U  ]
        [N_E,    N_var, N_U  ]
        [U_E,    U_N,   U_var]
        
        Args:
            msg: NavSatFix消息
            
        Returns:
            精度信息字典
        """
        cov = msg.position_covariance
        
        # 提取对角线方差
        e_var = cov[0]  # 东向方差
        n_var = cov[4]  # 北向方差
        u_var = cov[8]  # 上向方差
        
        # 计算标准差(精度)
        import math
        h_acc = math.sqrt(max(0, e_var + n_var)) if (e_var > 0 or n_var > 0) else 0.0
        v_acc = math.sqrt(max(0, u_var)) if u_var > 0 else 0.0
        
        # 计算PDOP (简化估算)
        p_dop = math.sqrt(h_acc**2 + v_acc**2) if (h_acc > 0 or v_acc > 0) else 0.0
        
        return {
            'h_acc': round(h_acc, 4),
            'v_acc': round(v_acc, 4),
            'p_dop': round(p_dop, 2)
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
            logger.info(f"NavSatFix订阅器关闭: {self.topic}")
        except Exception as e:
            logger.error(f"关闭NavSatFix订阅器时发生错误 {self.topic}: {e}")