#!/usr/bin/env python3
"""
地面站 WebSocket 中继代理 (Relay Proxy)
========================================
运行在地面工作站上，为无公网能力的机器人（水下 ROV / 无人机）提供透明转发。

架构:
    ROV (robot_agent) ──ws──► relay_proxy ──ws──► 云服务器

功能:
    1. 监听本地端口，接受机器人连接
    2. 建立到云服务器的对应连接
    3. 双向透明转发所有消息（传感器数据 + 控制指令）
    4. 支持多台机器人同时接入
    5. 内置本地监控页面（浏览器查看经过本地的数据流）

用法:
    pip install websockets
    python relay_proxy.py --listen 0.0.0.0:9000 --cloud ws://43.136.76.169

    机器人端将 --server 改为地面站地址:
    python robot_agent_ros2.py --server ws://地面站IP:9000 --robot-id rov1
"""

import asyncio
import websockets
import logging
import json
import time
import argparse
import socket
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format='[relay] %(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger('relay')

# 中继连接统计
class RelayStats:
    def __init__(self):
        self.robots: dict = {}       # robot_id -> {'up': N, 'down': N, 'since': ts}
        self.total_up = 0
        self.total_down = 0

    def register(self, robot_id: str):
        self.robots[robot_id] = {'up': 0, 'down': 0, 'since': time.time()}
        logger.info(f"[{robot_id}] 已注册 (当前在线: {len(self.robots)})")

    def unregister(self, robot_id: str):
        self.robots.pop(robot_id, None)
        logger.info(f"[{robot_id}] 已断开 (当前在线: {len(self.robots)})")

    def count_up(self, robot_id: str):
        self.total_up += 1
        if robot_id in self.robots:
            self.robots[robot_id]['up'] += 1

    def count_down(self, robot_id: str):
        self.total_down += 1
        if robot_id in self.robots:
            self.robots[robot_id]['down'] += 1

    def snapshot(self) -> dict:
        return {
            'robots': {
                rid: {'up': s['up'], 'down': s['down'],
                       'uptime': round(time.time() - s['since'])}
                for rid, s in self.robots.items()
            },
            'total_up': self.total_up,
            'total_down': self.total_down,
            'robot_count': len(self.robots),
        }

stats = RelayStats()


async def handle_rov(rov_ws: websockets.WebSocketServerProtocol, path: str) -> None:
    """
    处理一个水下机器人的连接:
    1. 从 path 提取 robot_id
    2. 连接到云服务器
    3. 双向转发消息
    """
    # 提取 robot_id: /ws/robot/rov1 -> rov1; /rov1 -> rov1
    parts = [p for p in path.strip('/').split('/') if p]
    robot_id = parts[-1] if parts else 'unknown'
    logger.info(f"[{robot_id}] 新连接: {rov_ws.remote_address}")

    # 连接云服务器
    cloud_url = f"{CLOUD_BASE}/ws/robot/{robot_id}"
    logger.info(f"[{robot_id}] 连接云服务器: {cloud_url}")

    try:
        async with websockets.connect(cloud_url, ping_interval=30, ping_timeout=10) as cloud_ws:
            stats.register(robot_id)

            # 双向转发
            async def rov_to_cloud():
                """机器人 → 地面站 → 云服务器"""
                try:
                    async for message in rov_ws:
                        await cloud_ws.send(message)
                        stats.count_up(robot_id)
                        # 调试: 打印消息类型（采样，避免刷屏）
                        try:
                            data = json.loads(message)
                            msg_type = data.get('type', '?')
                            if msg_type not in ('sensor_data',):
                                # 非数据消息全量打印
                                logger.debug(f"[{robot_id}] ↑ {msg_type}")
                        except Exception:
                            pass
                except websockets.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.error(f"[{robot_id}] 上行异常: {e}")

            async def cloud_to_rov():
                """云服务器 → 地面站 → 机器人（控制指令）"""
                try:
                    async for message in cloud_ws:
                        await rov_ws.send(message)
                        stats.count_down(robot_id)
                        try:
                            data = json.loads(message)
                            msg_type = data.get('type', '?')
                            logger.info(f"[{robot_id}] ↓ 云端指令: {msg_type}")
                        except Exception:
                            pass
                except websockets.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.error(f"[{robot_id}] 下行异常: {e}")

            # 并发运行两个转发方向，任一断开即结束
            done, pending = await asyncio.wait(
                [rov_to_cloud(), cloud_to_rov()],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except websockets.ConnectionClosed:
        logger.warning(f"[{robot_id}] 云端连接断开")
    except Exception as e:
        logger.error(f"[{robot_id}] 云服务器连接失败: {e}")
    finally:
        stats.unregister(robot_id)
        # 尝试关闭 ROV 连接
        try:
            await rov_ws.close()
        except Exception:
            pass


async def handle_monitor(monitor_ws: websockets.WebSocketServerProtocol, path: str) -> None:
    """本地监控页面 WebSocket —— 展示经过地面站的数据流统计。"""
    await monitor_ws.accept()
    logger.info(f"[monitor] 监控页面连接: {monitor_ws.remote_address}")
    try:
        while True:
            await monitor_ws.send(json.dumps({'type': 'relay_status', 'data': stats.snapshot()}))
            await asyncio.sleep(2)
    except websockets.ConnectionClosed:
        pass


async def handle_http(path: str, request_headers) -> tuple:
    """简单的 HTTP handler —— 提供本地监控页面。"""
    if path == '/' or path == '/monitor':
        html = MONITOR_HTML % {
            'hostname': socket.gethostname(),
            'ip': _get_local_ip(),
            'port': LISTEN_PORT,
            'cloud': CLOUD_BASE,
        }
        return 200, [('Content-Type', 'text/html; charset=utf-8')], html.encode('utf-8')
    return 404, [], b'Not Found'


MONITOR_HTML = r'''
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>地面站中继状态</title>
<style>
  body { font-family: system-ui, sans-serif; background: #0f1923; color: #e0e0e0; margin: 0; padding: 20px; }
  h1 { color: #00d2ff; font-size: 20px; margin-bottom: 5px; }
  .info { color: #888; font-size: 13px; margin-bottom: 20px; }
  .card { background: #1a2a3a; border-radius: 8px; padding: 16px; margin-bottom: 12px; border-left: 3px solid #00d2ff; }
  .robot { border-left-color: #4caf50; }
  .stat { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }
  .stat span:last-child { color: #00d2ff; font-weight: bold; }
  .empty { color: #666; text-align: center; padding: 40px; }
</style>
</head>
<body>
  <h1>地面站中继代理</h1>
  <div class="info">
    主机: %(hostname)s | IP: %(ip)s<br>
    监听端口: %(port)s | 云服务器: %(cloud)s
  </div>
  <div id="robots"></div>
  <script>
    const ws = new WebSocket('ws://' + location.host + '/monitor');
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data).data;
      let html = '';
      if (d.robot_count === 0) {
        html = '<div class="empty">等待机器人连接...</div>';
      } else {
        for (const [id, r] of Object.entries(d.robots)) {
          html += '<div class="card robot"><h3>机器人: ' + id + '</h3>';
          html += '<div class="stat"><span>上报消息</span><span>' + r.up + '</span></div>';
          html += '<div class="stat"><span>下发指令</span><span>' + r.down + '</span></div>';
          html += '<div class="stat"><span>运行时间</span><span>' + r.uptime + 's</span></div>';
          html += '</div>';
        }
      }
      html += '<div class="card"><div class="stat"><span>总上报</span><span>' + d.total_up + '</span></div>';
      html += '<div class="stat"><span>总下发</span><span>' + d.total_down + '</span></div></div>';
      document.getElementById('robots').innerHTML = html;
    };
  </script>
</body>
</html>
'''


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'unknown'


# ---- 全局配置（从命令行注入） ----
CLOUD_BASE = ''
LISTEN_PORT = 9000


async def main():
    global CLOUD_BASE, LISTEN_PORT

    parser = argparse.ArgumentParser(description='地面站 WebSocket 中继代理')
    parser.add_argument('--listen', default='0.0.0.0:9000',
                        help='监听地址:端口（默认: 0.0.0.0:9000）')
    parser.add_argument('--cloud', default='ws://43.136.76.169',
                        help='云服务器地址（默认: ws://43.136.76.169）')
    args = parser.parse_args()

    host, _, port_str = args.listen.partition(':')
    LISTEN_PORT = int(port_str) if port_str else 9000
    CLOUD_BASE = args.cloud.rstrip('/')

    logger.info("=" * 50)
    logger.info(f"  地面站中继代理启动")
    logger.info(f"  监听地址: {host}:{LISTEN_PORT}")
    logger.info(f"  云服务器: {CLOUD_BASE}")
    logger.info(f"  机器人使用: --server ws://{_get_local_ip()}:{LISTEN_PORT}")
    logger.info("=" * 50)

    server = await websockets.serve(
        handle_rov,
        host, LISTEN_PORT,
        process_request=handle_http,  # 提供 HTTP 监控页面
        ping_interval=30,
        ping_timeout=10,
    )

    logger.info(f"  监控页面: http://{_get_local_ip()}:{LISTEN_PORT}/")
    logger.info("  等待机器人连接...")
    await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(main())
