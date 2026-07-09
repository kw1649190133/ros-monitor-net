from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from contextlib import asynccontextmanager
import logging
import time
import os
import json
import argparse
from collections import deque

from src.websocket.connection_manager import ConnectionManager
from src.ros_bridge.node_manager import ROSNodeManager

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
ros_manager = None
connection_manager = ConnectionManager()

# 机器��连接追踪
robot_connections: dict = {}       # robot_id -> websocket
_robot_data_active = False         # 是否有机器人数据接入
_robot_state_lock = asyncio.Lock()  # 保护 robot_connections 和 _robot_data_active 的并发访问
ROBOT_HEARTBEAT_TIMEOUT = 30       # 机器人断连判定（秒）

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global ros_manager
    
    logger.info("Starting ROS Monitor Backend...")
    
    # 尝试 rosbridge 连接（可能失败，不影响启动）
    try:
        ros_manager = ROSNodeManager()
        await ros_manager.initialize()
        logger.info("ROS Node Manager initialized via rosbridge")
    except Exception as e:
        logger.warning(f"rosbridge 连接未就绪 ({e})，等待机器人主动上报数据")
        ros_manager = ROSNodeManager()
        ros_manager._running = True
        ros_manager._initialized = True
    
    # 启动后台广播任务（无论 rosbridge 是否就绪）
    asyncio.create_task(background_broadcast())
    
    yield
    
    # 关闭时清理
    logger.info("Shutting down ROS Monitor Backend...")
    if ros_manager:
        await ros_manager.shutdown()

# 创建FastAPI应用
app = FastAPI(
    title="ROS Monitor Backend",
    description="ROS远程监控后端服务",
    version="1.0.0",
    lifespan=lifespan
)

# 中间件配置 — CORS 白名单
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]
# 允许通过环境变量扩展
extra_origin = os.getenv("ALLOWED_ORIGIN", "")
if extra_origin:
    ALLOWED_ORIGINS.append(extra_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# API Key 配置（环境变量，逗号分隔）
_API_KEYS = set(k for k in os.getenv("API_KEYS", "").split(",") if k)

# 指令白名单
ALLOWED_COMMANDS = {"set_param", "emergency_stop", "waypoint", "ping"}

# 健康检查API
@app.get("/api/v1/health")
async def health_check():
    """健康检查接口"""
    ros_ready = (ros_manager is not None and ros_manager.is_connected()) or _robot_data_active
    robot_count = len(robot_connections)
    return {
        "success": True,
        "message": "ok",
        "ros_ready": ros_ready,
        "timestamp": time.time(),
        "websocket_clients": connection_manager.get_client_count(),
        "robot_connections": robot_count,
    }

# 系统状态API
@app.get("/api/v1/system/status")
async def system_status():
    """系统状态接口"""
    if ros_manager is None:
        return {
            "success": False,
            "message": "ROS Manager not initialized",
            "data": None
        }
    
    try:
        connection_info = ros_manager.get_connection_info()
        return {
            "success": True,
            "message": "System status retrieved successfully",
            "data": {
                "ros_connection": connection_info,
                "websocket_status": {
                    "total_clients": connection_manager.get_client_count(),
                    "subscription_info": connection_manager.get_subscription_info()
                },
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {
            "success": False,
            "message": f"Error retrieving system status: {str(e)}",
            "data": None
        }

# ---- 机器人数据上报端点 ----

@app.websocket("/ws/robot/{robot_id}")
async def robot_websocket_endpoint(websocket: WebSocket, robot_id: str):
    """机器人端 WebSocket 端点 —— 接收机器人推送的传感器数据。"""
    global _robot_data_active
    
    await websocket.accept()
    
    # API Key 认证（如果配置了密钥则强制校验）
    api_key = websocket.headers.get("x-api-key") or websocket.query_params.get("token")
    if _API_KEYS and (not api_key or api_key not in _API_KEYS):
        await websocket.send_json({"type": "error", "message": "Invalid API Key"})
        await websocket.close(code=4003)
        return
    robot_connections[robot_id] = {
        'ws': websocket, 'last_seen': time.time(),
        'bytes_received': 0,
        'bytes_history': deque(),      # (timestamp, bytes_received) — 用于5s滑动平均
        'rate_kbps': 0.0, 'last_rate_update': 0,
    }
    logger.info(f"机器人 [{robot_id}] 已连接 (当前在线: {len(robot_connections)}台)")
    
    try:
        while True:
            message = await websocket.receive_json()
            # 追踪流量：估算消息字节数，记录采样点用于滑动平均
            if robot_id in robot_connections:
                msg_bytes = len(json.dumps(message))
                conn = robot_connections[robot_id]
                conn['bytes_received'] += msg_bytes
                conn['bytes_history'].append((time.time(), conn['bytes_received']))
            await _handle_robot_message(robot_id, message)
    except WebSocketDisconnect:
        logger.info(f"机器人 [{robot_id}] 断开连接")
    except Exception as e:
        logger.error(f"机器人 [{robot_id}] 连接异常: {e}")
    finally:
        robot_connections.pop(robot_id, None)
        if not robot_connections:
            _robot_data_active = False
            logger.info("所有机器人已断线")

async def _handle_robot_message(robot_id: str, message: dict):
    """处理机器人上报的消息，存入 ros_manager.latest_data。"""
    global _robot_data_active
    
    msg_type = message.get('type', '')
    
    if msg_type == 'robot_register':
        hostname = message.get('hostname', robot_id)
        ip = message.get('ip', '')
        logger.info(f"机器人 [{robot_id}] 注册: {hostname} @ {ip}")
        async with _robot_state_lock:
            if robot_id in robot_connections:
                robot_connections[robot_id]['hostname'] = hostname
                robot_connections[robot_id]['ip'] = ip
                robot_connections[robot_id]['last_seen'] = time.time()
                # 确认注册
                try:
                    await robot_connections[robot_id]['ws'].send_json({
                        'type': 'robot_registered',
                        'message': f'欢迎 {hostname}，服务器已就绪',
                        'timestamp': time.time(),
                    })
                except Exception:
                    pass
        return
    
    elif msg_type == 'sensor_data':
        topic_name = message.get('topic_name', '')
        data = message.get('data', {})
        
        if ros_manager and topic_name:
            ros_manager._update_data(topic_name, data, robot_id=robot_id)
            async with _robot_state_lock:
                _robot_data_active = True
            # 广播 robot_list 给浏览器
            await _broadcast_robot_list()
            
        async with _robot_state_lock:
            if robot_id in robot_connections:
                robot_connections[robot_id]['last_seen'] = time.time()
        return
    
    elif msg_type == 'pong':
        async with _robot_state_lock:
            if robot_id in robot_connections:
                robot_connections[robot_id]['last_seen'] = time.time()
        return

# ---- 浏览器客户端端点 ----
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await connection_manager.connect(websocket, client_id)
    try:
        while True:
            # 接收客户端消息
            message = await websocket.receive_json()
            await handle_websocket_message(client_id, message)
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        connection_manager.disconnect(client_id)

async def handle_websocket_message(client_id: str, message: dict):
    """处理WebSocket消息"""
    try:
        msg_type = message.get("type")
        
        if msg_type == "subscribe":
            # 兼容两种格式: message.topics 和 message.data.topics
            topics = message.get("topics") or message.get("data", {}).get("topics", [])
            if not topics:
                logger.warning(f"Client {client_id} subscribe请求没有topics字段")
                topics = []
            
            await connection_manager.subscribe_topics(client_id, topics)
            logger.info(f"Client {client_id} subscribed to topics: {topics}")
            
            # 发送订阅确认
            await connection_manager.send_personal_message({
                "type": "subscription_confirmed",
                "topics": topics,
                "message": f"已成功订阅话题: {', '.join(topics)}"
            }, client_id)
            
        elif msg_type == "unsubscribe":
            # 兼容两种格式
            topics = message.get("topics") or message.get("data", {}).get("topics", [])
            if not topics:
                logger.warning(f"Client {client_id} unsubscribe请求没有topics字段")
                topics = []
            
            await connection_manager.unsubscribe_topics(client_id, topics)
            logger.info(f"Client {client_id} unsubscribed from topics: {topics}")
            
        elif msg_type == "request_system_status":
            # 发送系统状态
            if ros_manager:
                connection_info = ros_manager.get_connection_info()
                system_status = {
                    "type": "system_status",
                    "ros_ready": ros_manager.is_connected(),
                    "websocket_status": "connected",
                    "api_status": True,
                    "ros_info": connection_info,
                    "timestamp": time.time()
                }
            else:
                system_status = {
                    "type": "system_status",
                    "ros_ready": False,
                    "websocket_status": "connected",
                    "api_status": True,
                    "ros_info": None,
                    "timestamp": time.time()
                }
            
            await connection_manager.send_personal_message(system_status, client_id)
            
        elif msg_type == "ping":
            # 响应ping消息
            await connection_manager.send_personal_message({
                "type": "pong",
                "timestamp": time.time()
            }, client_id)
            
        elif msg_type == "camera_settings":
            # 处理相机设置更新
            if ros_manager:
                camera_id = message.get("camera_id")
                preview_height = message.get("preview_height")
                jpeg_quality = message.get("jpeg_quality")
                
                if camera_id and (preview_height is not None or jpeg_quality is not None):
                    success = ros_manager.update_camera_settings(camera_id, preview_height, jpeg_quality)
                    await connection_manager.send_personal_message({
                        "type": "camera_settings_updated",
                        "camera_id": camera_id,
                        "success": success,
                        "message": "相机设置已更新" if success else "相机设置更新失败"
                    }, client_id)
            else:
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": "ROS管理器未初始化"
                }, client_id)
        
        elif msg_type == "robot_command":
            # 浏览器 → 云端 → 地面站中继 → 机器人 控制指令
            target_robot = message.get("robot_id", "")
            command = message.get("command", {})
            
            if not target_robot:
                await connection_manager.send_personal_message({
                    "type": "error", "message": "缺少 target robot_id"
                }, client_id)
            elif target_robot not in robot_connections:
                await connection_manager.send_personal_message({
                    "type": "error", "message": f"机器人 {target_robot} 不在线"
                }, client_id)
            else:
                try:
                    payload = {
                        "type": "robot_command",
                        "command": command,
                        "from_client": client_id,
                        "timestamp": time.time(),
                    }
                    await robot_connections[target_robot]['ws'].send_json(payload)
                    await connection_manager.send_personal_message({
                        "type": "robot_command_sent",
                        "robot_id": target_robot,
                        "command": command,
                        "message": f"指令已下发到 {target_robot}"
                    }, client_id)
                    logger.info(f"指令下发: [{target_robot}] {command}")
                except Exception as e:
                    logger.error(f"指令下发失败 [{target_robot}]: {e}")
                    await connection_manager.send_personal_message({
                        "type": "error", "message": f"指令下发失败: {e}"
                    }, client_id)
        
        elif msg_type == "select_robot":
            # 浏览器选择查看某个机器人（前端过滤用）
            selected = message.get("robot_id", "")
            logger.info(f"Client {client_id} 选择机器人: {selected or '全部'}")
            await connection_manager.send_personal_message({
                "type": "robot_selected",
                "robot_id": selected,
                "message": f"已切换到 {selected}" if selected else "显示全部机器人",
            }, client_id)
                
        else:
            logger.warning(f"Unknown message type from {client_id}: {msg_type}")
            await connection_manager.send_personal_message({
                "type": "error",
                "message": f"未知的消息类型: {msg_type}"
            }, client_id)
            
    except Exception as e:
        logger.error(f"Error handling WebSocket message from {client_id}: {e}")
        await connection_manager.send_personal_message({
            "type": "error",
            "message": f"消息处理错误: {str(e)}"
        }, client_id)

async def background_broadcast():
    """后台数据广播任务 —— 按机器人逐个读取数据并推送给浏览器客户端。"""
    while True:
        try:
            robot_ids = ros_manager.get_robot_list() if ros_manager else []
            
            # 如果没有机器人数据但 rosbridge 模式活跃（兼容旧模式）
            has_any_data = len(robot_ids) > 0
            if not has_any_data and ros_manager and ros_manager.is_connected():
                has_any_data = True
                robot_ids = ['_direct']  # rosbridge 模式下的伪机器人 ID
            
            if ros_manager and (has_any_data or _robot_data_active):
                # 按机器人逐个广播
                for rid in robot_ids:
                    await _broadcast_for_robot(rid)
                
        except Exception as e:
            logger.error(f"Background broadcast error: {e}")
        
        await asyncio.sleep(0.5)  # 2Hz广播频率，降低带宽压力


async def _broadcast_for_robot(robot_id: str):
    """广播指定机器人的全部传感器数据。"""
    try:
        # 获取该机器人的最新数据
        camera_data = await ros_manager.get_latest_camera_data(robot_id) if robot_id != '_direct' else await ros_manager.get_latest_camera_data()
        lidar_data  = await ros_manager.get_latest_lidar_data(robot_id) if robot_id != '_direct' else await ros_manager.get_latest_lidar_data()
        imu_data    = await ros_manager.get_latest_imu_data(robot_id) if robot_id != '_direct' else await ros_manager.get_latest_imu_data()
        gnss_data   = await ros_manager.get_latest_gnss_data(robot_id) if robot_id != '_direct' else await ros_manager.get_latest_gnss_data()
        slam_data   = await ros_manager.get_latest_slam_data(robot_id) if robot_id != '_direct' else await ros_manager.get_latest_slam_data()

        # 公共标签
        robot_tag = {"robot_id": robot_id} if robot_id != '_direct' else {}

        # 相机
        if camera_data:
            for camera_id, data in camera_data.items():
                await connection_manager.broadcast_to_subscribers("camera", {
                    "type": "camera", "camera_id": camera_id,
                    "data": data, "timestamp": time.time(), **robot_tag,
                })
        # LiDAR
        if lidar_data:
            await connection_manager.broadcast_to_subscribers("lidar", {
                "type": "lidar", "data": lidar_data, "timestamp": time.time(), **robot_tag,
            })
        # IMU
        if imu_data:
            await connection_manager.broadcast_to_subscribers("imu", {
                "type": "imu", "data": imu_data, "timestamp": time.time(), **robot_tag,
            })
        # GNSS
        if gnss_data:
            await connection_manager.broadcast_to_subscribers("gnss", {
                "type": "gnss", "data": gnss_data, "timestamp": time.time(), **robot_tag,
            })
        # SLAM
        if slam_data:
            for key, msg_type in [('path', 'slam_path'), ('odometry', 'slam_odometry'), ('registered_cloud', 'slam_cloud')]:
                if key in slam_data:
                    await connection_manager.broadcast_to_subscribers("slam", {
                        "type": msg_type, "data": slam_data[key],
                        "timestamp": time.time(), **robot_tag,
                    })
    except Exception as e:
        logger.error(f"广播机器人 [{robot_id}] 失败: {e}")


async def _broadcast_robot_list():
    """广播在线机器人列表给所有浏览器客户端，附带流量信息。"""
    if not ros_manager:
        return
    robot_ids = ros_manager.get_robot_list()
    now = time.time()
    
    # 计算每台机器人的实时带宽（5秒滑动平均，1秒刷新一次）
    traffic = {}
    RATE_WINDOW = 5.0   # 5秒滑动窗口
    RATE_INTERVAL = 1.0  # 最小刷新间隔
    
    async with _robot_state_lock:
        conn_snapshot = dict(robot_connections)
    
    for rid, conn in conn_snapshot.items():
        conn = robot_connections[rid]
        total = conn.get('bytes_received', 0)
        history = conn.get('bytes_history', deque())
        
        # 只在间隔超过 1 秒时重新计算速率
        if now - conn.get('last_rate_update', 0) >= RATE_INTERVAL:
            conn['last_rate_update'] = now
            
            # 清理 5 秒前的旧采样点，保留至少 2 个点
            while len(history) > 2 and now - history[0][0] > RATE_WINDOW:
                history.popleft()
            
            # 计算滑动平均速率
            if len(history) >= 2:
                dt = history[-1][0] - history[0][0]
                db = history[-1][1] - history[0][1]
                rate = db / dt if dt > 0 else 0
            else:
                rate = 0
            
            conn['rate_kbps'] = round(rate / 1024, 1)
        
        traffic[rid] = {
            'total_kb': round(total / 1024, 1),
            'rate_kbps': conn.get('rate_kbps', 0),
        }
    
    msg = {
        "type": "robot_list_updated",
        "robots": robot_ids,
        "count": len(robot_ids),
        "traffic": traffic,
        "timestamp": now,
    }
    await connection_manager.broadcast_to_all(msg)

# ---- 云端控制 REST API ----

@app.post("/api/v1/robot/{robot_id}/command")
async def send_robot_command(robot_id: str, command: dict):
    """向指定机器人下发控制指令。
    
    POST /api/v1/robot/rov1/command
    {
        "action": "set_param",
        "param": "max_speed",
        "value": 0.5
    }
    """
    async with _robot_state_lock:
        if robot_id not in robot_connections:
            return {"success": False, "message": f"机器人 {robot_id} 不在线"}
        conn_ws = robot_connections[robot_id]['ws']
    
    # 指令白名单校验
    action = command.get("action", "")
    if action not in ALLOWED_COMMANDS:
        return {"success": False, "message": f"未授权的指令: {action}"}
    
    try:
        payload = {
            "type": "robot_command",
            "command": command,
            "from": "rest_api",
            "timestamp": time.time(),
        }
        await conn_ws.send_json(payload)
        logger.info(f"REST指令下发: [{robot_id}] {command}")
        return {"success": True, "message": f"指令已下发到 {robot_id}"}
    except Exception as e:
        logger.error(f"REST指令下发失败 [{robot_id}]: {e}")
        return {"success": False, "message": str(e)}


@app.get("/api/v1/robots")
async def list_robots():
    """列出所有在线机器人。"""
    async with _robot_state_lock:
        snap = dict(robot_connections)
    return {
        "success": True,
        "robots": [
            {"robot_id": rid, "hostname": info.get('hostname', '?'),
             "ip": info.get('ip', '?'), "last_seen": info.get('last_seen', 0),
             "bytes_received": info.get('bytes_received', 0),
             "bytes_rate": info.get('bytes_rate', 0)}
            for rid, info in snap.items()
        ],
        "count": len(snap),
    }


# 注册数据采集路由
from src.api.v1.data_collection import router as data_collection_router
app.include_router(data_collection_router, prefix="/api/v1")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ROS Monitor Backend")
    parser.add_argument("--port", type=int, default=int(os.getenv("ROS_MONITOR_PORT", "8001")),
                        help="Server port (env: ROS_MONITOR_PORT)")
    args = parser.parse_args()
    port = args.port
    
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )