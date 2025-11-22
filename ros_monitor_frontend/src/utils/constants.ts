// 应用常量配置

/**
 * 动态获取API主机地址
 * 优先级: 环境变量 > 运行时自动检测 > 默认值
 * @returns {string} API主机地址
 */
const getDefaultHost = (): string => {
  // 优先级1: 环境变量显式配置
  if (import.meta.env.VITE_API_HOST) {
    return import.meta.env.VITE_API_HOST;
  }
  
  // 优先级2: 运行时自动检测浏览器访问的hostname
  if (typeof window !== 'undefined' && window.location) {
    return window.location.hostname;
  }
  
  // 优先级3: SSR场景或其他fallback
  return 'localhost';
};

/**
 * 动态获取API端口
 * @returns {number} API端口号
 */
const getDefaultPort = (): number => {
  const envPort = import.meta.env.VITE_API_PORT;
  return envPort ? parseInt(envPort) : 8001;
};

// 从环境变量读取端口配置,默认使用8001
const API_PORT = getDefaultPort();
const API_HOST = getDefaultHost();

export const config = {
  // API配置
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || `http://${API_HOST}:${API_PORT}`,
  WS_URL: import.meta.env.VITE_WS_URL || `ws://${API_HOST}:${API_PORT}`,
  API_PORT: API_PORT,
  API_HOST: API_HOST,
  
  // 应用配置
  APP_TITLE: import.meta.env.VITE_APP_TITLE || 'ROS远程监控系统',
  
  // WebSocket配置
  WS_RECONNECT_ATTEMPTS: 5,
  WS_RECONNECT_INTERVAL: 3000,
  
  // 数据配置
  MAX_HISTORY_POINTS: 1000,
  CHART_UPDATE_INTERVAL: 100,
  HEALTH_CHECK_INTERVAL: 5000,
  
  // UI配置
  SIDEBAR_WIDTH: 240,
  HEADER_HEIGHT: 64,
};

export const SENSOR_TOPICS = {
  IMU: 'imu',
  CAMERA: 'camera',
  LIDAR: 'lidar',
} as const;

export const CONNECTION_STATUS = {
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  ERROR: 'error',
} as const;

export const CHART_COLORS = {
  X_AXIS: '#ff4d4f',
  Y_AXIS: '#52c41a', 
  Z_AXIS: '#1890ff',
  W_AXIS: '#722ed1',
} as const;

