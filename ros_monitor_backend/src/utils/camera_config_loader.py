#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相机配置加载器
负责从YAML配置文件加载相机话题配置
"""

import yaml
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class CameraConfigLoader:
    """相机配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径,如果为None则使用默认路径
        """
        if config_path is None:
            # 默认配置文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.config_path = os.path.join(current_dir, '..', 'config', 'camera_topics.yaml')
        else:
            self.config_path = config_path
        
        self.config = None
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            # 支持环境变量覆盖配置文件路径
            config_path = os.getenv('CAMERA_CONFIG_PATH', self.config_path)
            
            if not os.path.exists(config_path):
                logger.warning(f"配置文件不存在: {config_path}, 使用默认配置")
                self._use_default_config()
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            logger.info(f"成功加载相机配置文件: {config_path}")
            logger.info(f"配置了 {len(self.get_camera_topics())} 个相机话题")
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}, 使用默认配置")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用默认配置"""
        self.config = {
            'camera_topics': [
                {
                    'topic': '/left_camera/image_compressed/compressed',
                    'camera_id': 'left_camera',
                    'message_type': 'sensor_msgs/CompressedImage',
                    'description': '左侧相机压缩图像话题(默认)'
                },
                {
                    'topic': '/right_camera/image_compressed/compressed',
                    'camera_id': 'right_camera',
                    'message_type': 'sensor_msgs/CompressedImage',
                    'description': '右侧相机压缩图像话题(默认)'
                }
            ],
            'image_processing': {
                'jpeg_quality': 70,
                'max_width': 640,
                'enable_resize': True
            }
        }
        logger.info("使用默认相机配置")
    
    def get_camera_topics(self) -> List[Dict[str, Any]]:
        """
        获取所有相机话题配置
        
        Returns:
            相机话题配置列表
        """
        if not self.config or 'camera_topics' not in self.config:
            return []
        return self.config['camera_topics']
    
    def get_topic_list(self) -> List[str]:
        """
        获取所有相机话题名称列表
        
        Returns:
            话题名称列表
        """
        return [item['topic'] for item in self.get_camera_topics()]
    
    def get_camera_id_by_topic(self, topic: str) -> Optional[str]:
        """
        根据话题名称获取相机ID
        
        Args:
            topic: 话题名称
            
        Returns:
            相机ID,如果未找到返回None
        """
        for item in self.get_camera_topics():
            if item['topic'] == topic:
                return item['camera_id']
        return None
    
    def get_topic_by_camera_id(self, camera_id: str) -> Optional[str]:
        """
        根据相机ID获取话题名称
        
        Args:
            camera_id: 相机ID
            
        Returns:
            话题名称,如果未找到返回None
        """
        for item in self.get_camera_topics():
            if item['camera_id'] == camera_id:
                return item['topic']
        return None
    
    def get_image_processing_params(self) -> Dict[str, Any]:
        """
        获取图像处理参数
        
        Returns:
            图像处理参数字典
        """
        if not self.config or 'image_processing' not in self.config:
            return {
                'jpeg_quality': 70,
                'max_width': 640,
                'enable_resize': True
            }
        return self.config['image_processing']
    
    def reload_config(self):
        """重新加载配置文件"""
        logger.info("重新加载相机配置...")
        self._load_config()


# 创建全局配置实例
camera_config = CameraConfigLoader()
