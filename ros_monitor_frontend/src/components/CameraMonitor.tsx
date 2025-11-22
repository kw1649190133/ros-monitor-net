import React from 'react';
import { Row, Col, Typography } from 'antd';
import { CameraOutlined } from '@ant-design/icons';
import CameraViewer from './CameraViewer';

const { Title, Text } = Typography;

export const CameraMonitor: React.FC = () => {
  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>
          <CameraOutlined style={{ marginRight: 8 }} />
          相机监控系统
        </Title>
        <Text type="secondary">
          实时监控双目相机数据流，支持图像预览、设置调整和数据下载
        </Text>
      </div>

      {/* 相机视图 */}
      <Row gutter={[24, 24]}>
        <Col span={12}>
          <CameraViewer 
            cameraId="left_camera" 
            className="camera-viewer"
          />
        </Col>
        <Col span={12}>
          <CameraViewer 
            cameraId="right_camera" 
            className="camera-viewer"
          />
        </Col>
      </Row>
    </div>
  );
};

export default CameraMonitor;