"""
Rosbridge WebSocket 客户端
通过 rosbridge_server 远程订阅 ROS topic，替代本地 rospy 直连。
"""

import asyncio
import logging
import time
import roslibpy
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)


class RosbridgeClient:
    """连接到远程 rosbridge_server，通过 WebSocket 订阅/取消订阅 ROS topic。"""

    def __init__(self, host: str = 'localhost', port: int = 9090):
        self.host = host
        self.port = port
        self.ros: Optional[roslibpy.Ros] = None
        self._topics: Dict[str, roslibpy.Topic] = {}
        self._lock = asyncio.Lock()
        self._connected = asyncio.Event()

    async def connect(self, timeout: float = 10.0) -> None:
        """连接到 rosbridge_server，异步等待连接就绪。"""
        self.ros = roslibpy.Ros(host=self.host, port=self.port)
        self._connected.clear()

        def on_connected() -> None:
            logger.info(f"已连接到 rosbridge ws://{self.host}:{self.port}")
            self._connected.set()

        def on_close() -> None:
            logger.warning("rosbridge 连接已关闭")
            self._connected.clear()

        def on_error(err: Any) -> None:
            logger.error(f"rosbridge 连接错误: {err}")

        self.ros.on('connection', on_connected)
        self.ros.on('close', on_close)
        self.ros.on('error', on_error)

        self.ros.run()  # 后台线程启动 WebSocket 连接

        # 异步等待连接就绪（使用 asyncio.Event 替代 busy-wait）
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.ros.terminate()
            self.ros = None
            raise ConnectionError(
                f"连接 rosbridge ws://{self.host}:{self.port} 超时 ({timeout}s)。"
                f"请确认机器人端已运行: roslaunch rosbridge_server rosbridge_websocket.launch"
            )

        logger.info(f"rosbridge 连接就绪")

    async def subscribe(self, topic: str, msg_type: str, callback: Callable[[dict], None]) -> None:
        """订阅一个 ROS topic。"""
        if self.ros is None:
            raise RuntimeError("rosbridge 未连接，请先调用 connect()")

        listener = roslibpy.Topic(self.ros, topic, msg_type)
        listener.subscribe(callback)
        async with self._lock:
            self._topics[topic] = listener
        logger.info(f"通过 rosbridge 订阅: {topic} ({msg_type})")

    async def unsubscribe(self, topic: str) -> None:
        """取消订阅某个 topic。"""
        async with self._lock:
            if topic in self._topics:
                self._topics[topic].unsubscribe()
                del self._topics[topic]
                logger.info(f"取消订阅: {topic}")

    @property
    def is_connected(self) -> bool:
        """rosbridge 是否已连接。"""
        return self.ros is not None and self.ros.is_connected

    async def get_subscribed_topics(self) -> list:
        """返回当前已订阅的 topic 列表。"""
        async with self._lock:
            return list(self._topics.keys())

    async def close(self) -> None:
        """关闭 rosbridge 连接，取消所有订阅。"""
        async with self._lock:
            for topic in list(self._topics.keys()):
                try:
                    self._topics[topic].unsubscribe()
                except Exception:
                    pass
            self._topics.clear()

        if self.ros is not None:
            try:
                self.ros.terminate()
            except Exception:
                pass
            self.ros = None

        self._connected.clear()
        logger.info("rosbridge 客户端已关闭")
