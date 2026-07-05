from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from contextlib import asynccontextmanager
import logging
import time
import os

from src.websocket.connection_manager import ConnectionManager
from src.ros_bridge.node_manager import ROSNodeManager
from src.api.v1.data_collection import router as data_collection_router

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
ros_manager = None
connection_manager = ConnectionManager()

# 机器人连接追踪
robot_connections: dict = {}       # robot_id -> websocket
_robot_data_active = False         # 是否有机器人数据接入
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

# 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    robot_connections[robot_id] = {'ws': websocket, 'last_seen': time.time()}
    logger.info(f"机器人 [{robot_id}] 已连接 (当前在线: {len(robot_connections)}台)")
    
    try:
        while True:
            message = await websocket.receive_json()
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
            ros_manager._update_data(topic_name, data)
            _robot_data_active = True
            
        if robot_id in robot_connections:
            robot_connections[robot_id]['last_seen'] = time.time()
        return
    
    elif msg_type == 'pong':
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
    """后台数据广播任务 —— 从 ros_manager.latest_data 读取并推送给浏览器客户端。"""
    while True:
        try:
            if ros_manager and (ros_manager.is_connected() or _robot_data_active):
                # 获取最新的传感器数据
                camera_data = await ros_manager.get_latest_camera_data()
                lidar_data = await ros_manager.get_latest_lidar_data()
                imu_data = await ros_manager.get_latest_imu_data()
                gnss_data = await ros_manager.get_latest_gnss_data()
                
                # 调试日志: 检查GNSS数据获取
                if gnss_data:
                    logger.info(f"获取到GNSS数据: RTK={gnss_data.get('rtk_status')}, 卡星={gnss_data.get('quality', {}).get('num_sv', 0)}")
                
                # 推送给订阅的客户端
                if camera_data:
                    logger.info(f"广播相机数据: {list(camera_data.keys())}")
                    for camera_id, data in camera_data.items():
                        message = {
                            "type": "camera",
                            "camera_id": camera_id,
                            "data": data,
                            "timestamp": time.time()
                        }
                        await connection_manager.broadcast_to_subscribers("camera", message)
                        logger.info(f"相机 {camera_id} 数据已广播，帧数: {data.get('sequence', 0)}")
                else:
                    logger.debug("没有相机数据可广播")
                
                if lidar_data:
                    message = {
                        "type": "lidar",
                        "data": lidar_data,
                        "timestamp": time.time()
                    }
                    await connection_manager.broadcast_to_subscribers("lidar", message)
                    
                if imu_data:
                    message = {
                        "type": "imu",
                        "data": imu_data,
                        "timestamp": time.time()
                    }
                    await connection_manager.broadcast_to_subscribers("imu", message)
                
                # 广播GNSS数据
                if gnss_data:
                    message = {
                        "type": "gnss",
                        "data": gnss_data,
                        "timestamp": time.time()
                    }
                    await connection_manager.broadcast_to_subscribers("gnss", message)
                    logger.info(f"GNSS数据已广播, RTK状态: {gnss_data.get('rtk_status', 'UNKNOWN')}, 卡星数: {gnss_data.get('quality', {}).get('num_sv', 0)}")
                else:
                    logger.debug("没有GNSS数据可广播")

                # 广播SLAM数据(轨迹、位姿、点云)
                slam_data = await ros_manager.get_latest_slam_data()
                if slam_data:
                    # 广播Path数据
                    if 'path' in slam_data:
                        message = {
                            "type": "slam_path",
                            "data": slam_data['path'],
                            "timestamp": time.time()
                        }
                        await connection_manager.broadcast_to_subscribers("slam", message)
                        logger.debug(f"Path数据已广播, 点数: {slam_data['path'].get('total_poses', 0)}")

                    # 广播Odometry数据
                    if 'odometry' in slam_data:
                        message = {
                            "type": "slam_odometry",
                            "data": slam_data['odometry'],
                            "timestamp": time.time()
                        }
                        await connection_manager.broadcast_to_subscribers("slam", message)
                        logger.debug(f"Odometry数据已广播")

                    # 广播RegisteredCloud数据
                    if 'registered_cloud' in slam_data:
                        message = {
                            "type": "slam_cloud",
                            "data": slam_data['registered_cloud'],
                            "timestamp": time.time()
                        }
                        await connection_manager.broadcast_to_subscribers("slam", message)
                        logger.debug(f"RegisteredCloud数据已广播, 点数: {slam_data['registered_cloud'].get('sampled_points', 0)}")

        except Exception as e:
            logger.error(f"Background broadcast error: {e}")
        
        await asyncio.sleep(0.1)  # 10Hz推送频率

# 注册数据采集路由
from src.api.v1.data_collection import router as data_collection_router
app.include_router(data_collection_router, prefix="/api/v1")

if __name__ == "__main__":
    # 从环境变量或命令行参数获取端口
    import sys
    port = 8001  # 默认端口改为8001
    
    # 支持从环境变量读取
    if os.getenv('ROS_MONITOR_PORT'):
        port = int(os.getenv('ROS_MONITOR_PORT'))
    
    # 支持命令行参数 --port
    for i, arg in enumerate(sys.argv):
        if arg == '--port' and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
            break
    
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )