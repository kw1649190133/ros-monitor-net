import { useSensorStore } from '../stores/useSensorStore';
import { useSystemStore } from '../stores/useSystemStore';
import { config } from '../utils/constants';
import type { GNSSData } from '../types/gnss';

export interface WSMessage {
  type: string;
  timestamp: string;
  data: any;
}

export class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 3000;
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
          console.log('✅ WebSocket connected successfully');
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          
          // 发送认证消息
          const token = localStorage.getItem('access_token');
          if (token) {
            this.send({
              type: 'auth',
              timestamp: new Date().toISOString(),
              data: { token }
            });
          }
          
          // 更新系统状态
          useSystemStore.getState().updateConnectionStatus('websocket', true);
          
          resolve();
        };
        
        this.ws.onmessage = (event) => {
          try {
            const message: WSMessage = JSON.parse(event.data);
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
  
  private handleMessage(message: WSMessage | any): void {
    const { type, data } = message;
    
    switch (type) {
      case 'connected':
        console.log('WebSocket authentication successful');
        break;
        
      case 'subscribed':
      case 'subscription_confirmed':
        // 后端可能返回两种类型
        const topics = message.topics || (data && data.topics) || [];
        console.log('✅ 话题订阅成功:', topics);
        if (message.message) {
          console.log('📝', message.message);
        }
        break;
      
      case 'unsubscribed':
        const unsubTopics = message.topics || (data && data.topics) || [];
        console.log('❌ 取消订阅:', unsubTopics);
        if (message.message) {
          console.log('📝', message.message);
        }
        break;
        
      case 'camera':
        this.handleCameraData(data || message);
        break;
        
      case 'lidar':
        this.handleLidarData(data || message);
        break;
      
      case 'gnss':
        this.handleGNSSData(data || message);
        break;
        
      case 'system_status':
        this.handleSystemStatus(data || message);
        break;
        
      case 'ack':
        console.log('Message acknowledged:', data || message);
        break;
      
      case 'error':
        console.error('❌ 服务器错误:', message.message || data);
        break;
        
      default:
        console.warn('⚠️  未知消息类型:', type, message);
    }
  }
  

  
  private handleCameraData(data: any): void {
    const sensorStore = useSensorStore.getState();
    if (data.camera_id) {
      sensorStore.updateCameraData(data.camera_id, {
        camera_id: data.camera_id,
        timestamp: data.timestamp,
        sequence: data.sequence || 0,
        encoding: data.encoding,
        width: data.width,
        height: data.height,
        data: data.data,
        compressed: data.compressed || false
      });
    }
  }
  
  private handleLidarData(data: any): void {
    const sensorStore = useSensorStore.getState();
    sensorStore.updateLidarData({
      timestamp: data.timestamp,
      frame_id: data.frame_id || 'map',
      point_count: data.point_count,
      points: data.data
    });
  }
  
  private handleSystemStatus(data: any): void {
    const systemStore = useSystemStore.getState();
    systemStore.updatePerformanceMetrics({
      dataRate: data.data_rate || 0,
      errorCount: data.error_count || 0
    });
  }
  
  private handleGNSSData(data: any): void {
    const sensorStore = useSensorStore.getState();
    sensorStore.updateGNSSData({
      rtk_status: data.rtk_status,
      quality: data.quality,
      position: data.position,
      accuracy: data.accuracy,
      velocity: data.velocity,
      time: data.time,
      timestamp: data.timestamp,
      sequence: data.sequence
    });
  }
  
  send(message: WSMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.error('WebSocket is not connected');
    }
  }
  
  subscribe(topics: string[]): void {
    if (!this.isConnected()) {
      console.warn('⚠️ WebSocket还未连接，无法订阅:', topics);
      return;
    }
    
    this.send({
      type: 'subscribe',
      timestamp: new Date().toISOString(),
      data: { topics }
    });
    console.log('📡 发送订阅请求:', topics);
  }
  
  unsubscribe(topics: string[]): void {
    this.send({
      type: 'unsubscribe',
      timestamp: new Date().toISOString(),
      data: { topics }
    });
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
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
  
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// 单例WebSocket服务
export const wsService = new WebSocketService();
