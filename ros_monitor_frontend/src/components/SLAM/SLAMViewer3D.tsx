import React, { useRef, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid, Line } from '@react-three/drei';
import * as THREE from 'three';
import { useSensorStore } from '../../stores/useSensorStore';

// 坐标轴组件 - Z轴朝上，X前，Y左 的右手系
const CoordinateAxes: React.FC<{ size?: number }> = ({ size = 2 }) => {
  return (
    <group>
      {/* X轴 - 红色 (前) */}
      <Line
        points={[[0, 0, 0], [size, 0, 0]]}
        color="red"
        lineWidth={2}
      />
      {/* Y轴 - 绿色 (左) */}
      <Line
        points={[[0, 0, 0], [0, size, 0]]}
        color="green"
        lineWidth={2}
      />
      {/* Z轴 - 蓝色 (上) */}
      <Line
        points={[[0, 0, 0], [0, 0, size]]}
        color="blue"
        lineWidth={2}
      />
    </group>
  );
};

// 轨迹线组件
const TrajectoryLine: React.FC = () => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  
  const points = useMemo(() => {
    if (!slam?.path?.poses?.length) return [];
    return slam?.path.poses.map(pose => [
      pose.position.x,
      pose.position.y,
      pose.position.z
    ] as [number, number, number]);
  }, [slam?.path]);
  
  if (points.length < 2) return null;
  
  return (
    <Line
      points={points}
      color="#00ff00"
      lineWidth={2}
    />
  );
};

// 当前位姿标记组件
const CurrentPoseMarker: React.FC = () => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  const groupRef = useRef<THREE.Group>(null);
  
  if (!slam?.odometry?.pose) return null;
  
  const { position, orientation } = slam?.odometry.pose;
  
  // 四元数转欧拉角
  const quaternion = new THREE.Quaternion(
    orientation.x,
    orientation.y,
    orientation.z,
    orientation.w
  );
  
  return (
    <group
      ref={groupRef}
      position={[position.x, position.y, position.z]}
      quaternion={quaternion}
    >
      {/* 机器人位姿坐标轴 */}
      <CoordinateAxes size={0.5} />
      {/* 机器人位置标记 */}
      <mesh>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshStandardMaterial color="#ff0000" />
      </mesh>
    </group>
  );
};

// 当前帧点云组件 - 固定红色显示
const CurrentFrameCloud: React.FC = () => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  const pointsRef = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();

    // 当前帧点云
    const cloud = slam?.registeredCloud;
    if (!cloud?.points?.length) {
      geo.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      return geo;
    }

    const positions = new Float32Array(cloud.points.length * 3);
    cloud.points.forEach((point, i) => {
      positions[i * 3] = point[0];
      positions[i * 3 + 1] = point[1];
      positions[i * 3 + 2] = point[2];
    });

    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    return geo;
  }, [slam?.registeredCloud]);

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
      // 当前lidar桢点的大小
        size={0.04}
        color="#ff0000"
        sizeAttenuation={true}
        transparent={true}
        opacity={1.0}
      />
    </points>
  );
};

// 历史地图点云组件 - 使用真实RGB颜色
const HistoryMapCloud: React.FC = () => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  const pointsRef = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();

    // 只使用历史点云 (排除最新一帧，最新一帧用CurrentFrameCloud显示)
    const historyCount = slam?.cloudHistory?.length || 0;
    if (historyCount <= 1) {
      geo.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      geo.setAttribute('color', new THREE.Float32BufferAttribute([], 3));
      return geo;
    }

    // 历史点云不包含最后一帧(当前帧)
    // const historyData = slam?.cloudHistory.slice(0, -1);
 
    const historyData = slam?.cloudHistory;

    // 计算总点数
    let totalPoints = 0;
    historyData.forEach(cloud => {
      totalPoints += cloud.points.length;
    });

    if (totalPoints === 0) {
      geo.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      geo.setAttribute('color', new THREE.Float32BufferAttribute([], 3));
      return geo;
    }

    const positions = new Float32Array(totalPoints * 3);
    const colors = new Float32Array(totalPoints * 3);

    let idx = 0;
    historyData.forEach(cloud => {
      const hasColors = cloud.colors && cloud.colors.length === cloud.points.length;

      cloud.points.forEach((point, i) => {
        positions[idx * 3] = point[0];
        positions[idx * 3 + 1] = point[1];
        positions[idx * 3 + 2] = point[2];

        // 使用真实RGB颜色，如果没有则使用默认颜色
        if (hasColors && cloud.colors) {
          colors[idx * 3] = cloud.colors[i][0] / 255;     // R
          colors[idx * 3 + 1] = cloud.colors[i][1] / 255; // G
          colors[idx * 3 + 2] = cloud.colors[i][2] / 255; // B
        } else {
          // 默认白灰色
          colors[idx * 3] = 0.7;
          colors[idx * 3 + 1] = 0.7;
          colors[idx * 3 + 2] = 0.7;
        }

        idx++;
      });
    });

    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    return geo;
  }, [slam?.cloudHistory]);

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
      // 点的大小
        size={0.03}
        vertexColors={true}
        sizeAttenuation={true}
        transparent={true}
        opacity={0.9}
      />
    </points>
  );
};

// 场景内容组件
const SceneContent: React.FC = () => {
  return (
    <>
      {/* 光源 */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      
      {/* 网格 - 旋转到XY平面 (Z朝上) */}
      <Grid
        args={[100, 100]}
        cellSize={1}
        cellThickness={0.5}
        cellColor="#6f6f6f"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#9d4b4b"
        fadeDistance={50}
        infiniteGrid
        rotation={[-Math.PI / 2, 0, 0]}
      />
      
      {/* 原点坐标轴 */}
      <CoordinateAxes size={2} />
      
      {/* 轨迹线 */}
      <TrajectoryLine />
      
      {/* 当前位姿 */}
      <CurrentPoseMarker />

      {/* 历史地图点云 - 真实RGB颜色 */}
      <HistoryMapCloud />

      {/* 当前帧点云 - 红色 */}
      <CurrentFrameCloud />

      {/* 控制器 */}
      <OrbitControls
        enableDamping
        dampingFactor={0.05}
        minDistance={1}
        maxDistance={100}
      />
    </>
  );
};

// 主3D查看器组件
export const SLAMViewer3D: React.FC<{ style?: React.CSSProperties }> = ({ style }) => {
  return (
    <div style={{ width: '100%', height: '500px', ...style }}>
      {/* 相机位置调整为Z朝上视角: 从后上方看向原点 */}
      <Canvas camera={{ position: [-5, -5, 5], up: [0, 0, 1], fov: 60 }}>
        <SceneContent />
      </Canvas>
    </div>
  );
};

export default SLAMViewer3D;

