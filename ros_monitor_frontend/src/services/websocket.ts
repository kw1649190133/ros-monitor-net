import { useSensorStore } from '../stores/useSensorStore';
import { useSystemStore } from '../stores/useSystemStore';
import { config } from '../utils/constants';
import type { InboundMessage, OutboundMessage } from '../types/websocket';

export class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = config.WS_RECONNECT_ATTEMPTS;
  private reconnectInterval = config.WS_RECONNECT_INTERVAL;
  private clientId: string;
  private url: string = '';
  private isConnecting = false;
  
  constructor(clientId?: string) {
    this.clientId = clientId || this.generateClientId();
  }
  
  private generateClientId(): string {
    return `frontend_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
  
  connect(host: string = config.API_HOST, port: number = config.API_PORT): Promise<void> {
    if (this.isConnecting) {
      return Promise.reject(new Error('Connection already in progress'));
    }
    
    this.isConnecting = true;
    this.url = `ws://${host}:${port}/ws/${this.clientId}`;
    
    return new Promise((resolve, reject) => {
      try {
        console.log('Connecting to WebSocket:', this.url);
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
          console.log('WebSocket connected successfully');
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          
          useSystemStore.getState().updateConnectionStatus('websocket', true);
          
          resolve();
        };
        
        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as InboundMessage;
            this.handleMessage(message);
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };
        
        this.ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.code, event.reason);
          this.isConnecting = false;
          useSystemStore.getState().updateConnectionStatus('websocket', false);
          this.attemptReconnect();
        };
        
        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.isConnecting = false;
          reject(error);
        };
        
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }
  
  private handleMessage(message: InboundMessage): void {
    const type = message.type;
    const robotId: string = ('robot_id' in message) ? (message as { robot_id?: string }).robot_id || '_direct' : '_direct';
    
    switch (type) {
      case 'connected':
        console.log('WebSocket authentication successful');
        break;
        
      case 'subscribed':
      case 'subscription_confirmed':
        console.log('话题订阅成功:', message.topics);
        break;
      
      case 'unsubscribed':
        console.log('取消订阅:', message.topics);
        break;

      case 'robot_list_updated':
        this.handleRobotListUpdated(message);
        break;

      case 'robot_command_sent':
        console.log(`指令已下发到 [${message.robot_id}]:`, message.command);
        break;
        
      case 'camera':
        this.handleCameraData(robotId, message);
        break;
        
      case 'lidar':
        this.handleLidarData(robotId, message);
        break;
      
      case 'gnss':
        this.handleGNSSData(robotId, message);
        break;

      case 'slam_path':
        this.handlePathData(robotId, message);
        break;

      case 'slam_odometry':
        this.handleOdometryData(robotId, message);
        break;

      case 'slam_cloud':
        this.handleRegisteredCloudData(robotId, message);
        break;

      case 'system_status':
        this.handleSystemStatus(message);
        break;

      case 'ack':
        console.log('Message acknowledged:', message.message);
        break;

      case 'error':
        console.error('服务器错误:', message.message);
        break;

      default:
        console.warn('未知消息类型:', type, message);
    }
  }
  
  private handleRobotListUpdated(msg: import('../types/websocket').WSRobotListMessage): void {
    const robots = msg.robots;
    console.log('在线机器人列表更新:', robots);
    useSensorStore.getState().setRobotList(robots);
    const systemStore = useSystemStore.getState();
    robots.forEach((rid: string) => systemStore.updateRobotConnection(rid, 'ros', true));
    if (msg.traffic) {
      systemStore.updateRobotTraffic(msg.traffic);
    }
  }

  private handleCameraData(robotId: string, msg: import('../types/websocket').WSCameraMessage): void {
    const { camera_id, timestamp, sequence = 0, encoding, width, height, data, compressed = false } = msg.data;
    if (camera_id) {
      useSensorStore.getState().updateCameraData(robotId, camera_id, {
        camera_id, timestamp, sequence, encoding, width, height, data, compressed,
      });
    }
  }
  
  private handleLidarData(robotId: string, msg: import('../types/websocket').WSLidarMessage): void {
    const { timestamp, frame_id = 'map', point_count, data: points } = msg.data;
    useSensorStore.getState().updateLidarData(robotId, {
      timestamp, frame_id, point_count, points,
    });
  }
  
  private handleSystemStatus(msg: import('../types/websocket').WSSystemStatusMessage): void {
    useSystemStore.getState().updatePerformanceMetrics({
      dataRate: 0,
      errorCount: 0,
    });
  }
  
  private handleGNSSData(robotId: string, msg: import('../types/websocket').WSGNSSMessage): void {
    const d = msg.data;
    useSensorStore.getState().updateGNSSData(robotId, {
      rtk_status: d.rtk_status,
      quality: d.quality,
      position: d.position,
      accuracy: d.accuracy,
      velocity: d.velocity,
      time: d.time,
      timestamp: d.timestamp,
      sequence: d.sequence,
    });
  }

  private handlePathData(robotId: string, msg: import('../types/websocket').WSPathMessage): void {
    const d = msg.data;
    useSensorStore.getState().updatePathData(robotId, {
      topic: d.topic,
      timestamp: d.timestamp,
      frame_id: d.frame_id,
      sequence: d.sequence,
      total_poses: d.total_poses,
      sampled_poses: d.sampled_poses,
      poses: d.poses,
    });
  }

  private handleOdometryData(robotId: string, msg: import('../types/websocket').WSOdometryMessage): void {
    const d = msg.data;
    useSensorStore.getState().updateOdometryData(robotId, {
      topic: d.topic,
      timestamp: d.timestamp,
      frame_id: d.frame_id,
      child_frame_id: d.child_frame_id,
      sequence: d.sequence,
      pose: d.pose,
      twist: d.twist,
    });
  }

  private handleRegisteredCloudData(robotId: string, msg: import('../types/websocket').WSCloudMessage): void {
    const d = msg.data;
    useSensorStore.getState().updateRegisteredCloudData(robotId, {
      topic: d.topic,
      timestamp: d.timestamp,
      frame_id: d.frame_id,
      sequence: d.sequence,
      total_points: d.total_points,
      sampled_points: d.sampled_points,
      points: d.points,
      fields: d.fields,
      colors: d.colors,
      has_rgb: d.has_rgb,
    });
  }

  send(message: OutboundMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.error('WebSocket is not connected');
    }
  }
  
  subscribe(topics: string[]): void {
    if (!this.isConnected()) {
      console.warn('WebSocket还未连接，无法订阅:', topics);
      return;
    }
    this.send({ type: 'subscribe', data: { topics } });
    console.log('发送订阅请求:', topics);
  }
  
  unsubscribe(topics: string[]): void {
    this.send({ type: 'unsubscribe', data: { topics } });
  }
  
  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        if (this.url) {
          this.connect(this.url.replace('ws://', '').split(':')[0], 
                      parseInt(this.url.split(':')[2].split('/')[0]))
            .catch(console.error);
        }
      }, this.reconnectInterval);
    } else {
      console.error('Max reconnection attempts reached');
    }
  }
  
  disconnect(): void {
    this.reconnectAttempts = 0;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
  
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsService = new WebSocketService();
