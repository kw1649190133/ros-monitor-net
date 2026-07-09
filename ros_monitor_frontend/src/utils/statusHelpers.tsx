// 共享 UI 辅助函数，避免多组件重复定义

import { Badge } from 'antd';
import React from 'react';

/** 连接状态 Badge 组件 */
export const StatusBadge: React.FC<{ connected: boolean }> = ({ connected }) => (
  <Badge
    status={connected ? 'success' : 'error'}
    text={connected ? '正常' : '离线'}
  />
);

/** 获取连接状态颜色 */
export function getStatusColor(connected: boolean): string {
  return connected ? '#52c41a' : '#ff4d4f';
}

/** 获取连接文本 */
export function getStatusText(connected: boolean): string {
  return connected ? '已连接' : '未连接';
}

/** 获取延迟颜色 */
export function getLatencyColor(latency: number): string {
  if (latency < 100) return '#52c41a';
  if (latency < 300) return '#faad14';
  return '#ff4d4f';
}
