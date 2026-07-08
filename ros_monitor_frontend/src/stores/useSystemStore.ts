import { create } from 'zustand';
import type { ConnectionInfo } from '../types/api';

interface SystemStore {
  // 连接状态（全局 + 按机器人）
  connection: ConnectionInfo;
  robotConnections: Record<string, ConnectionInfo>;

  // 流量监控（按机器人）
  robotTraffic: Record<string, { total_kb: number; rate_kbps: number }>;

  // 性能指标
  performance: {
    wsLatency: number;
    dataRate: number;
    errorCount: number;
    uptime: number;
  };

  // UI 状态
  ui: {
    sidebarCollapsed: boolean;
    theme: 'light' | 'dark';
    currentPage: string;
  };

  // Actions — 全局连接
  updateConnectionStatus: (type: keyof ConnectionInfo, status: boolean) => void;
  updateLatency: (latency: number) => void;
  updatePerformanceMetrics: (metrics: Partial<SystemStore['performance']>) => void;

  // Actions — 按机器人连接
  updateRobotConnection: (robotId: string, type: keyof ConnectionInfo, status: boolean) => void;

  // Actions — 流量监控
  updateRobotTraffic: (traffic: Record<string, { total_kb: number; rate_kbps: number }>) => void;

  // UI Actions
  toggleSidebar: () => void;
  setCurrentPage: (page: string) => void;
  incrementErrorCount: () => void;
  resetErrorCount: () => void;
}

const defaultConnection: ConnectionInfo = {
  websocket: false,
  api: false,
  ros: false,
  latency: 0,
};

export const useSystemStore = create<SystemStore>((set) => ({
  connection: { ...defaultConnection },

  robotConnections: {},

  robotTraffic: {},

  performance: {
    wsLatency: 0,
    dataRate: 0,
    errorCount: 0,
    uptime: 0,
  },

  ui: {
    sidebarCollapsed: false,
    theme: 'dark',
    currentPage: 'dashboard',
  },

  // 全局连接（浏览器 WS + API 状态）
  updateConnectionStatus: (type: keyof ConnectionInfo, status: boolean) => set((state) => ({
    connection: { ...state.connection, [type]: status },
  })),

  updateLatency: (latency: number) => set((state) => ({
    connection: { ...state.connection, latency },
    performance: { ...state.performance, wsLatency: latency },
  })),

  updatePerformanceMetrics: (metrics: Partial<SystemStore['performance']>) => set((state) => ({
    performance: { ...state.performance, ...metrics },
  })),

  // 按机器人连接状态
  updateRobotConnection: (robotId: string, type: keyof ConnectionInfo, status: boolean) => set((state) => {
    const current = state.robotConnections[robotId] || { ...defaultConnection };
    return {
      robotConnections: {
        ...state.robotConnections,
        [robotId]: { ...current, [type]: status },
      },
    };
  }),

  updateRobotTraffic: (traffic) => set({ robotTraffic: traffic }),

  toggleSidebar: () => set((state) => ({
    ui: { ...state.ui, sidebarCollapsed: !state.ui.sidebarCollapsed },
  })),

  setCurrentPage: (page: string) => set((state) => ({
    ui: { ...state.ui, currentPage: page },
  })),

  incrementErrorCount: () => set((state) => ({
    performance: { ...state.performance, errorCount: state.performance.errorCount + 1 },
  })),

  resetErrorCount: () => set((state) => ({
    performance: { ...state.performance, errorCount: 0 },
  })),
}));
