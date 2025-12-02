import React, { useEffect } from 'react';
import { Card, Row, Col, Typography, Statistic, Tag, Space, Button, Tooltip, InputNumber } from 'antd';
import {
  AimOutlined,
  EnvironmentOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  CloudOutlined,
  FieldTimeOutlined
} from '@ant-design/icons';
import { useSensorStore } from '../../stores/useSensorStore';
import { wsService } from '../../services/websocket';
import SLAMViewer3D from './SLAMViewer3D';

const { Title, Text } = Typography;

export const SLAMMonitor: React.FC = () => {
  const { slam, clearSLAMData, setDecayTime } = useSensorStore();
  
  // 订阅SLAM数据
  useEffect(() => {
    console.log('🎯 订阅SLAM话题...');
    wsService.subscribe(['slam']);
    
    return () => {
      console.log('🎯 取消订阅SLAM话题...');
      wsService.unsubscribe(['slam']);
    };
  }, []);
  
  // 格式化位置数据
  const formatPosition = (pos: { x: number; y: number; z: number } | undefined) => {
    if (!pos) return '-';
    return `(${pos.x.toFixed(3)}, ${pos.y.toFixed(3)}, ${pos.z.toFixed(3)})`;
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
          <Tag color={slam.status.connected ? 'green' : 'red'}>
            {slam.status.connected ? '已连接' : '未连接'}
          </Tag>
          <Tooltip title="清除数据">
            <Button icon={<ReloadOutlined />} onClick={clearSLAMData}>
              清除
            </Button>
          </Tooltip>
        </Space>
      </div>
      
      {/* 状态统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title="轨迹点数"
              value={slam.path?.total_poses || 0}
              prefix={<EnvironmentOutlined />}
              suffix="个"
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title="当前帧点云"
              value={slam.registeredCloud?.sampled_points || 0}
              prefix={<CloudOutlined />}
              suffix="个"
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title="累积点云帧数"
              value={slam.cloudHistory?.length || 0}
              prefix={<CloudOutlined />}
              suffix="帧"
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title="当前位置"
              value={formatPosition(slam.odometry?.pose?.position)}
              prefix={<AimOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary">
                <FieldTimeOutlined style={{ marginRight: 4 }} />
                Decay Time (秒)
              </Text>
            </div>
            <InputNumber
              min={1}
              max={10000}
              value={slam.decayTime}
              onChange={(value) => setDecayTime(value || 1000)}
              style={{ width: '100%' }}
              addonAfter="s"
            />
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
            帧ID: {slam.odometry?.frame_id || '-'}
          </Text>
        }
      >
        <SLAMViewer3D style={{ height: 600 }} />
        
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
                <Text code>{formatPosition(slam.odometry?.pose?.position)}</Text>
              </Col>
              <Col span={12}>
                <Text strong>速度:</Text>
                <br />
                <Text code>
                  {slam.odometry?.twist?.linear ? 
                    `(${slam.odometry.twist.linear.x.toFixed(3)}, ${slam.odometry.twist.linear.y.toFixed(3)}, ${slam.odometry.twist.linear.z.toFixed(3)})` 
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
                <Text strong>Path帧数:</Text> {slam.path?.sequence || 0}
              </Col>
              <Col span={12}>
                <Text strong>Odom帧数:</Text> {slam.odometry?.sequence || 0}
              </Col>
            </Row>
            <Row style={{ marginTop: 8 }}>
              <Col span={12}>
                <Text strong>Cloud帧数:</Text> {slam.registeredCloud?.sequence || 0}
              </Col>
              <Col span={12}>
                <Text strong>采样点:</Text> {slam.registeredCloud?.sampled_points || 0}/{slam.registeredCloud?.total_points || 0}
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default SLAMMonitor;

