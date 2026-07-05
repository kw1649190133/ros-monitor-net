"""
PointCloud2 消息解析器
将 rosbridge 传输的 JSON 格式 PointCloud2（data 为 base64 编码的二进制）解析为点坐标列表。
"""

import base64
import struct
import math
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def parse_pointcloud2(msg_json: dict, max_points: int = 5000) -> Tuple[List[List[float]], Optional[List[List[int]]], int]:
    """解析 rosbridge JSON 格式的 PointCloud2 消息。

    rosbridge 将 PointCloud2.data（二进制数组）编码为 base64 字符串。
    本函数解码二进制数据并提取点坐标（和可选的 RGB 颜色）。

    Args:
        msg_json: rosbridge 回调中的 JSON dict
        max_points: 最大采样点数（超过则随机降采样）

    Returns:
        (points, colors, total_points)
        - points: [[x, y, z], ...]
        - colors: [[r, g, b], ...] 或 None（无颜色字段时）
        - total_points: 原始点云总点数
    """
    fields = msg_json.get('fields', [])
    point_step = msg_json.get('point_step', 0)
    data_b64 = msg_json.get('data', '')
    is_dense = msg_json.get('is_dense', True)

    if not data_b64 or point_step == 0:
        return [], None, 0

    try:
        raw_data = base64.b64decode(data_b64)
    except Exception as e:
        logger.error(f"PointCloud2 base64 解码失败: {e}")
        return [], None, 0

    total_points = len(raw_data) // point_step

    # 解析字段偏移
    field_info = {}
    for f in fields:
        name = f.get('name', '')
        field_info[name] = {
            'offset': f.get('offset', 0),
            'datatype': f.get('datatype', 7),  # 7 = FLOAT32
        }

    has_rgb = 'rgb' in field_info

    # 决定是否需要降采样
    if total_points > max_points:
        import random
        sample_ratio = max_points / total_points
    else:
        sample_ratio = 1.0

    points = []
    colors = [] if has_rgb else None

    for i in range(total_points):
        if sample_ratio < 1.0 and random.random() > sample_ratio:
            continue
        if len(points) >= max_points:
            break

        offset = i * point_step

        # 提取 x, y, z
        try:
            x = struct.unpack_from('f', raw_data, offset + field_info['x']['offset'])[0]
            y = struct.unpack_from('f', raw_data, offset + field_info['y']['offset'])[0]
            z = struct.unpack_from('f', raw_data, offset + field_info['z']['offset'])[0]
        except struct.error:
            continue

        # 跳过 NaN/Inf（非稠密点云需要）
        if not is_dense and (math.isnan(x) or math.isnan(y) or math.isnan(z)):
            continue
        if not is_dense and (math.isinf(x) or math.isinf(y) or math.isinf(z)):
            continue

        points.append([x, y, z])

        # 提取 RGB 颜色（如果有）
        if has_rgb:
            try:
                rgb_float = struct.unpack_from('f', raw_data, offset + field_info['rgb']['offset'])[0]
                # ROS 中 rgb 是 packed float，格式为 BGR
                rgb_int = struct.unpack('I', struct.pack('f', rgb_float))[0]
                b = (rgb_int >> 0) & 0xFF
                g = (rgb_int >> 8) & 0xFF
                r = (rgb_int >> 16) & 0xFF
                colors.append([r, g, b])
            except struct.error:
                colors.append([255, 255, 255])

    return points, colors, total_points
