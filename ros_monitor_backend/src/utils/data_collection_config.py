"""
数据采集配置加载器
"""

import os
import yaml
import logging
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)

class DataCollectionConfig:
    """数据采集配置类"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            backend_dir = Path(__file__).resolve().parent.parent.parent
            config_path = backend_dir / "config" / "data_collection.yaml"
        
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self):
        """加载YAML配置文件"""
        try:
            if not self.config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"成功加载配置文件: {self.config_path}")
                return config
                
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self):
        """返回默认配置"""
        return {
            "script_config": {
                "script_dir": "/home/ycs/work/ROS_monitor/script",
                "allowed_scripts": ["start_all.sh", "stop_all.sh"],
                "execution_timeout": 30
            },
            "data_collection": {
                "start": {
                    "script_name": "start_all.sh",
                    "timeout": 30
                },
                "stop": {
                    "script_name": "stop_all.sh",
                    "timeout": 30
                }
            }
        }
    
    @property
    def script_dir(self) -> str:
        """获取脚本目录"""
        return self._config.get("script_config", {}).get("script_dir", "/home/ycs/work/ROS_monitor/script")
    
    @property
    def allowed_scripts(self) -> List[str]:
        """获取允许执行的脚本列表"""
        return self._config.get("script_config", {}).get("allowed_scripts", ["start_all.sh", "stop_all.sh"])
    
    @property
    def execution_timeout(self) -> int:
        """获取默认执行超时时间"""
        return self._config.get("script_config", {}).get("execution_timeout", 30)

# 全局配置实例
data_collection_config = DataCollectionConfig()
