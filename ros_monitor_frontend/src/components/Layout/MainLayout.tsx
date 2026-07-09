import { debugLog, errorLog } from '../../utils/logger';
import React, { useEffect } from 'react';

import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { SystemStatus } from '../Dashboard/SystemStatus';
import { ConnectionStatus } from '../Dashboard/ConnectionStatus';
import { OverviewPanel } from '../Dashboard/OverviewPanel';
import CameraMonitor from '../CameraMonitor';
import DataCollectionControl from '../Sensors/DataCollectionControl';
import GNSSStatusPanel from '../Sensors/GNSSStatusPanel';
import SLAMMonitor from '../SLAM/SLAMMonitor';
import { useSystemStore } from '../../stores/useSystemStore';
import { apiService } from '../../services/api';
import { wsService } from '../../services/websocket';
import { config } from '../../utils/constants';

export const MainLayout: React.FC = () => {
  const { ui } = useSystemStore();
  const currentPage = ui.currentPage;

  // 初始化WebSocket连接
  useEffect(() => {
    const connectWebSocket = async () => {
      try {
        debugLog('🔌 正在连接WebSocket...');
        await wsService.connect(config.API_HOST, config.API_PORT);
        debugLog('✅ WebSocket全局连接成功');
        
        // 订阅所有传感器话题（多机模式下必须显式订阅才能接收广播数据）
        wsService.subscribe(['camera', 'lidar', 'gnss', 'imu', 'slam']);
        
        // 请求系统状态
        wsService.send({
          type: 'request_system_status',
          timestamp: new Date().toISOString(),
        });
      } catch (error) {
        errorLog('❌ WebSocket连接失败:', error);
      }
    };

    connectWebSocket();

    return () => {
      debugLog('🔌 断开WebSocket连接...');
      wsService.disconnect();
    };
  }, []);

  // 初始化API健康检查
  useEffect(() => {
    debugLog('🚀 启动API健康检查...');
    
    // 开始定期健康检查（每10秒检查一次）
    apiService.startHealthCheck(10000);
    
    // 组件卸载时停止健康检查
    return () => {
      debugLog('🛑 停止API健康检查...');
      apiService.stopHealthCheck();
    };
  }, []);

  const renderContent = () => {
    switch (currentPage) {
      case 'overview':
        return <OverviewPanel />;
      case 'dashboard':
        return <SystemStatus />;
      case 'camera':
        return <CameraMonitor />;
      case 'gnss':
        return <GNSSStatusPanel />;
      case 'slam':
        return <SLAMMonitor />;
      case 'connection':
        return <ConnectionStatus />;
      case 'data-collection':
        return <DataCollectionControl />;
      case 'settings':
        return (
          <div style={{ padding: '24px', textAlign: 'center' }}>
            <h2>系统设置</h2>
            <p>设置功能开发中...</p>
          </div>
        );
      default:
        return <SystemStatus />;
    }
  };

  return (
    <div style={{ 
      display: 'flex', 
      minHeight: '100vh',
      backgroundColor: '#f0f2f5'
    }}>
      {/* 侧边栏 */}
      <Sidebar />
      
      {/* 主内容区域 */}
      <div style={{ 
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        marginLeft: ui.sidebarCollapsed ? 80 : 240,
        transition: 'margin-left 0.2s ease',
        minWidth: 0, // 防止flex子元素溢出
      }}>
        {/* 顶部导航 */}
        <Header />
        
        {/* 主内容 */}
        <div style={{
          flex: 1,
          padding: '24px',
          marginTop: '64px', // Header高度
          overflow: 'auto',
          minHeight: 'calc(100vh - 64px)',
        }}>
          <div style={{
            background: '#fff',
            borderRadius: '8px',
            padding: '24px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            minHeight: 'calc(100vh - 112px)', // 减去Header和padding
          }}>
            {renderContent()}
          </div>
        </div>
      </div>
    </div>
  );
};

