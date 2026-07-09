import React, { useRef, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid, Line } from '@react-three/drei';
import * as THREE from 'three';
import { useSensorStore } from '../../stores/useSensorStore';

// 坐标轴组件 - Z轴朝上，X前，Y左 的右手系
const CoordinateAxes: React.FC<{ size?: number }> = ({ size = 2 }) => {
  return (
    <group>
      <Line points={[[0, 0, 0], [size, 0, 0]]} color="red" lineWidth={2} />
      <Line points={[[0, 0, 0], [0, size, 0]]} color="green" lineWidth={2} />
      <Line points={[[0, 0, 0], [0, 0, size]]} color="blue" lineWidth={2} />
    </group>
  );
};

// 轨迹线组件
const TrajectoryLine: React.FC = React.memo(() => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  
  const points = useMemo(() => {
    if (!slam?.path?.poses?.length) return [];
    return slam.path.poses.map(pose => [
      pose.position.x, pose.position.y, pose.position.z
    ] as [number, number, number]);
  }, [slam?.path]);
  
  if (points.length < 2) return null;
  
  return <Line points={points} color="#00ff00" lineWidth={2} />;
};

// 当前位姿标记
const CurrentPoseMarker: React.FC = React.memo(() => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  const groupRef = useRef<THREE.Group>(null);
  
  if (!slam?.odometry?.pose) return null;
  
  const { position, orientation } = slam.odometry.pose;
  const quaternion = new THREE.Quaternion(
    orientation.x, orientation.y, orientation.z, orientation.w
  );
  
  return (
    <group ref={groupRef} position={[position.x, position.y, position.z]} quaternion={quaternion}>
      <CoordinateAxes size={0.5} />
      <mesh>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshStandardMaterial color="#ff0000" />
      </mesh>
    </group>
  );
};

// 当前帧点云 - 固定红色
const CurrentFrameCloud: React.FC = React.memo(() => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  const pointsRef = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const cloud = slam?.registeredCloud;
    if (!cloud?.points?.length) {
      geo.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      return geo;
    }
    const positions = new Float32Array(cloud.points.length * 3);
    cloud.points.forEach((point: number[], i: number) => {
      positions[i * 3] = point[0];
      positions[i * 3 + 1] = point[1];
      positions[i * 3 + 2] = point[2];
    });
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    return geo;
  }, [slam?.registeredCloud]);

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial size={0.04} color="#ff0000" sizeAttenuation />
    </points>
  );
};

// 历史点云 - 支持手动调整最大点数和帧数
const HistoryMapCloud: React.FC<{ maxPoints?: number; maxFrames?: number }> = ({
  maxPoints = 10000,
  maxFrames = 20,
}) => {
  const { robotData, activeRobotId } = useSensorStore();
  const slam = activeRobotId ? robotData[activeRobotId]?.slam : null;
  const pointsRef = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const allHistory = slam?.cloudHistory || [];
    if (allHistory.length <= 1) {
      geo.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      geo.setAttribute('color', new THREE.Float32BufferAttribute([], 3));
      return geo;
    }

    // 限制帧数（取最近 N 帧）
    const historyData = allHistory.slice(-maxFrames);
    const pointsPerFrame = Math.ceil(maxPoints / historyData.length);

    // 先算总点数
    let totalPoints = 0;
    const steps = historyData.map((cloud) => {
      const n = cloud.points.length;
      const step = n <= pointsPerFrame ? 1 : Math.ceil(n / pointsPerFrame);
      for (let i = 0; i < n; i += step) totalPoints++;
      return step;
    });

    if (totalPoints === 0) {
      geo.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
      geo.setAttribute('color', new THREE.Float32BufferAttribute([], 3));
      return geo;
    }

    const positions = new Float32Array(totalPoints * 3);
    const colors = new Float32Array(totalPoints * 3);
    let idx = 0;

    historyData.forEach((cloud, fi) => {
      const hasColors = cloud.colors && cloud.colors.length === cloud.points.length;
      const step = steps[fi];
      const n = cloud.points.length;

      for (let i = 0; i < n; i += step) {
        positions[idx * 3]     = cloud.points[i][0];
        positions[idx * 3 + 1] = cloud.points[i][1];
        positions[idx * 3 + 2] = cloud.points[i][2];

        if (hasColors && cloud.colors?.[i]) {
          colors[idx * 3]     = cloud.colors[i][0] / 255;
          colors[idx * 3 + 1] = cloud.colors[i][1] / 255;
          colors[idx * 3 + 2] = cloud.colors[i][2] / 255;
        } else {
          colors[idx * 3]     = 0.7;
          colors[idx * 3 + 1] = 0.7;
          colors[idx * 3 + 2] = 0.7;
        }
        idx++;
      }
    });

    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    return geo;
  }, [slam?.cloudHistory, maxPoints, maxFrames]);

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial size={0.03} vertexColors sizeAttenuation transparent opacity={0.9} />
    </points>
  );
};

// 场景内容
const SceneContent: React.FC<{ maxCloudPoints: number; maxCloudFrames: number }> = ({
  maxCloudPoints,
  maxCloudFrames,
}) => {
  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <Grid
        args={[100, 100]} cellSize={1} cellThickness={0.5} cellColor="#6f6f6f"
        sectionSize={5} sectionThickness={1} sectionColor="#9d4b4b"
        fadeDistance={50} infiniteGrid
        rotation={[-Math.PI / 2, 0, 0]}
      />
      <CoordinateAxes size={2} />
      <TrajectoryLine />
      <CurrentPoseMarker />
      <HistoryMapCloud maxPoints={maxCloudPoints} maxFrames={maxCloudFrames} />
      <CurrentFrameCloud />
      <OrbitControls enableDamping dampingFactor={0.05} minDistance={1} maxDistance={100} />
    </>
  );
};

// 主3D查看器 - 接受渲染参数
export const SLAMViewer3D: React.FC<{
  style?: React.CSSProperties;
  maxCloudPoints?: number;
  maxCloudFrames?: number;
}> = ({ style, maxCloudPoints = 10000, maxCloudFrames = 20 }) => {
  return (
    <div style={{ width: '100%', height: '500px', ...style }}>
      <Canvas camera={{ position: [-5, -5, 5], up: [0, 0, 1], fov: 60 }}>
        <SceneContent maxCloudPoints={maxCloudPoints} maxCloudFrames={maxCloudFrames} />
      </Canvas>
    </div>
  );
};

export default SLAMViewer3D;
