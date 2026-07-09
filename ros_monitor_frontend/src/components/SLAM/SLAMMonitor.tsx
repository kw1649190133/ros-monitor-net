import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Typography, Statistic, Tag, Space, Button, Tooltip, InputNumber } from 'antd';
import {
  AimOutlined,
  EnvironmentOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  CloudOutlined,
  SettingOutlined
} from '@ant-design/icons';
import { useSensorStore } from '../../stores/useSensorStore';
import { wsService } from '../../services/websocket';
import SLAMViewer3D from './SLAMViewer3D';

const { Title, Text } = Typography;

export const SLAMMonitor: React.FC = () => {
  const { robotData, activeRobotId, clearSLAMData } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  
  // 可手动调整的参数 —— 根据机器性能和网络带宽动态调整
  const [maxCloudPoints, setMaxCloudPoints] = useState(10000);
  const [maxCloudFrames, setMaxCloudFrames] = useState(20);
  
  // 订阅SLAM数据
  useEffect(() => {
    console.log('🎯 订阅SLAM话题...');
    wsService.subscribe(['slam']);
    
    return () => {
      console.log('🎯 取消订阅SLAM话题...');
      wsService.unsubscribe(['slam']);
    };
  }, []);
  
  // 格式化位置数据 —— 固定长度防止负号导致换行
  const formatPosition = (pos: { x: number; y: number; z: number } | undefined) => {
    if (!pos) return '-';
    return `(${pos.x.toFixed(2)}, ${pos.y.toFixed(2)}, ${pos.z.toFixed(2)})`;
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 标题区域 */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2}>
            <NodeIndexOutlined style={{ marginRight: 8 }} />
            SLAM可视化监控
          </Title>
          <Text type="secondary">
            实时显示机器人轨迹、位姿和点云地图
          </Text>
        </div>
        <Space>
          <Tag color={slam?.status.connected ? 'green' : 'red'}>
            {slam?.status.connected ? '已连接' : '未连接'}
          </Tag>
          <Tooltip title="清除数据">
            <Button icon={<ReloadOutlined />} onClick={() => clearSLAMData(activeRobotId || "")}>
              清除
            </Button>
          </Tooltip>
        </Space>
      </div>
      
      {/* 状态统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="轨迹点数"
              value={slam?.path?.total_poses || 0}
              prefix={<EnvironmentOutlined />}
              suffix="个"
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="当前帧点云"
              value={slam?.registeredCloud?.sampled_points || 0}
              prefix={<CloudOutlined />}
              suffix="个"
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="累积帧数"
              value={slam?.cloudHistory?.length || 0}
              prefix={<CloudOutlined />}
              suffix="帧"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="当前位置"
              value={formatPosition(slam?.odometry?.pose?.position)}
              prefix={<AimOutlined />}
              valueStyle={{ fontFamily: 'monospace', fontSize: '24px', whiteSpace: 'nowrap' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title={<span><SettingOutlined /> 渲染参数</span>}>
            <Text type="secondary" style={{ fontSize: '11px', display: 'block', marginBottom: '8px' }}>
              修改后自动生效，根据机器性能调整
            </Text>
            <Row gutter={[8, 8]}>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: '11px' }}>最大点数</Text>
                <InputNumber
                  size="small"
                  min={500}
                  max={500000}
                  step={500}
                  value={maxCloudPoints}
                  onChange={v => setMaxCloudPoints(v || 3000)}
                  style={{ width: '100%' }}
                />
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: '11px' }}>最大帧数</Text>
                <InputNumber
                  size="small"
                  min={1}
                  max={200}
                  step={1}
                  value={maxCloudFrames}
                  onChange={v => setMaxCloudFrames(v || 10)}
                  style={{ width: '100%' }}
                />
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
      
      {/* 3D可视化区域 */}
      <Card
        title={
          <Space>
            <NodeIndexOutlined />
            <span>3D轨迹与点云可视化</span>
          </Space>
        }
        extra={
          <Text type="secondary">
            帧ID: {slam?.odometry?.frame_id || '-'}
          </Text>
        }
      >
        <SLAMViewer3D
          style={{ height: 600 }}
          maxCloudPoints={maxCloudPoints}
          maxCloudFrames={maxCloudFrames}
        />
        
        {/* 图例 */}
        <div style={{ marginTop: 16, padding: '8px 16px', background: '#f5f5f5', borderRadius: 4 }}>
          <Space size="large">
            <Space>
              <div style={{ width: 16, height: 3, background: 'red' }} />
              <Text type="secondary">X轴</Text>
            </Space>
            <Space>
              <div style={{ width: 16, height: 3, background: 'green' }} />
              <Text type="secondary">Y轴</Text>
            </Space>
            <Space>
              <div style={{ width: 16, height: 3, background: 'blue' }} />
              <Text type="secondary">Z轴</Text>
            </Space>
            <Space>
              <div style={{ width: 16, height: 3, background: '#00ff00' }} />
              <Text type="secondary">运动轨迹</Text>
            </Space>
            <Space>
              <div style={{ width: 8, height: 8, background: '#ff0000', borderRadius: '50%' }} />
              <Text type="secondary">当前帧点云</Text>
            </Space>
            <Space>
              <div style={{ width: 8, height: 8, background: 'linear-gradient(90deg, #888, #fff)', borderRadius: '50%' }} />
              <Text type="secondary">历史地图(RGB)</Text>
            </Space>
          </Space>
        </div>
      </Card>
      
      {/* 详细信息 */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col span={12}>
          <Card title="位姿信息" size="small">
            <Row>
              <Col span={12}>
                <Text strong>位置:</Text>
                <br />
                <Text code>{formatPosition(slam?.odometry?.pose?.position)}</Text>
              </Col>
              <Col span={12}>
                <Text strong>速度:</Text>
                <br />
                <Text code>
                  {slam?.odometry?.twist?.linear ? 
                    `(${slam?.odometry.twist.linear.x.toFixed(3)}, ${slam?.odometry.twist.linear.y.toFixed(3)}, ${slam?.odometry.twist.linear.z.toFixed(3)})` 
                    : '-'}
                </Text>
              </Col>
            </Row>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="帧信息" size="small">
            <Row>
              <Col span={12}>
                <Text strong>Path帧数:</Text> {slam?.path?.sequence || 0}
              </Col>
              <Col span={12}>
                <Text strong>Odom帧数:</Text> {slam?.odometry?.sequence || 0}
              </Col>
            </Row>
            <Row style={{ marginTop: 8 }}>
              <Col span={12}>
                <Text strong>Cloud帧数:</Text> {slam?.registeredCloud?.sequence || 0}
              </Col>
              <Col span={12}>
                <Text strong>采样点:</Text> {slam?.registeredCloud?.sampled_points || 0}/{slam?.registeredCloud?.total_points || 0}
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default SLAMMonitor;

