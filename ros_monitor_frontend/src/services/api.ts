import { useSystemStore } from '../stores/useSystemStore';
import { config } from '../utils/constants';

export interface APIHealthResponse {
  success: boolean;
  message: string;
  ros_ready: boolean;
  timestamp: number;
  websocket_clients: number;
  robot_connections?: number;
}

export interface RobotListResponse {
  success: boolean;
  robots: Array<{ robot_id: string; hostname: string; ip: string; last_seen: number }>;
  count: number;
}

export interface SystemStatusResponse {
  success: boolean;
  message: string;
  data: {
    ros_connection: any;
    websocket_status: {
      total_clients: number;
      subscription_info: any;
    };
    timestamp: number;
  } | null;
}

class APIService {
  private baseURL: string;
  private healthCheckInterval: number | null = null;
  private isChecking = false;

  constructor(host: string = config.API_HOST, port: number = config.API_PORT) {
    this.baseURL = `http://${host}:${port}`;
  }

  /**
   * 检查API健康状态
   */
  async checkHealth(): Promise<APIHealthResponse | null> {
    try {
      const response = await fetch(`${this.baseURL}/api/v1/health`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: AbortSignal.timeout(5000), // 5秒超时
      });

      if (response.ok) {
        const data: APIHealthResponse = await response.json();
        return data;
      } else {
        console.error('API health check failed:', response.status, response.statusText);
        return null;
      }
    } catch (error) {
      console.error('API health check error:', error);
      return null;
    }
  }

  /**
   * 获取系统状态
   */
  async getSystemStatus(): Promise<SystemStatusResponse | null> {
    try {
      const response = await fetch(`${this.baseURL}/api/v1/system/status`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: AbortSignal.timeout(5000), // 5秒超时
      });

      if (response.ok) {
        const data: SystemStatusResponse = await response.json();
        return data;
      } else {
        console.error('System status check failed:', response.status, response.statusText);
        return null;
      }
    } catch (error) {
      console.error('System status check error:', error);
      return null;
    }
  }

  /**
   * 开始定期健康检查
   */
  startHealthCheck(intervalMs: number = 10000): void {
    if (this.healthCheckInterval) {
      this.stopHealthCheck();
    }

    this.healthCheckInterval = window.setInterval(async () => {
      if (this.isChecking) return;
      
      this.isChecking = true;
      await this.performHealthCheck();
      this.isChecking = false;
    }, intervalMs);

    // 立即执行一次检查
    this.performHealthCheck();
  }

  /**
   * 停止健康检查
   */
  stopHealthCheck(): void {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
  }

  /**
   * 执行健康检查并更新状态
   */
  private async performHealthCheck(): Promise<void> {
    const systemStore = useSystemStore.getState();
    
    try {
      const healthResponse = await this.checkHealth();
      
      if (healthResponse && healthResponse.success) {
        systemStore.updateConnectionStatus('api', true);
        
        const rosReady = healthResponse.ros_ready;
        systemStore.updateConnectionStatus('ros', rosReady);
        
        console.log('API健康检查成功:', {
          api: true, ros: rosReady,
          websocket_clients: healthResponse.websocket_clients,
          robot_connections: healthResponse.robot_connections,
        });
      } else {
        systemStore.updateConnectionStatus('api', false);
        systemStore.updateConnectionStatus('ros', false);
      }
    } catch (error) {
      console.error('健康检查执行失败:', error);
      systemStore.updateConnectionStatus('api', false);
      systemStore.updateConnectionStatus('ros', false);
    }
  }

  /**
   * 获取在线机器人列表
   */
  async getRobotList(): Promise<RobotListResponse | null> {
    try {
      const response = await fetch(`${this.baseURL}/api/v1/robots`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(5000),
      });
      if (response.ok) return await response.json();
      return null;
    } catch {
      return null;
    }
  }

  /**
   * 向指定机器人下发指令
   */
  async sendCommand(robotId: string, command: Record<string, any>): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseURL}/api/v1/robot/${robotId}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(command),
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * 更新API基础URL
   */
  updateBaseURL(host: string, port: number): void {
    this.baseURL = `http://${host}:${port}`;
    console.log('API基础URL已更新:', this.baseURL);
  }
}

// 创建全局API服务实例
export const apiService = new APIService();

// 导出默认实例
export default apiService;
