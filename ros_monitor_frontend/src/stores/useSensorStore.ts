import { create } from 'zustand';
import type { CameraData, LidarData, SensorStatus } from '../types/sensors';
import type { GNSSData } from '../types/gnss';


interface SensorStore {
  // 相机数据
  camera: {
    left: CameraData | null;
    right: CameraData | null;
    status: SensorStatus;
  };
  
  // 激光雷达数据
  lidar: {
    latest: LidarData | null;
    status: SensorStatus;
  };
  
  // GNSS数据
  gnss: {
    latest: GNSSData | null;
    history: GNSSData[];
    status: SensorStatus;
  };
  
  // Actions
  updateCameraData: (camera: 'left' | 'right', data: CameraData) => void;
  updateLidarData: (data: LidarData) => void;
  updateGNSSData: (data: GNSSData) => void;
  updateSensorStatus: (sensor: 'camera' | 'lidar' | 'gnss', status: Partial<SensorStatus>) => void;
  clearGNSSData: () => void;
  clearAllData: () => void;
}

const initialSensorStatus: SensorStatus = {
  connected: false,
  lastUpdate: 0,
  frequency: 0,
  errorCount: 0,
};

export const useSensorStore = create<SensorStore>((set) => ({
  camera: {
    left: null,
    right: null,
    status: { ...initialSensorStatus },
  },
  
  lidar: {
    latest: null,
    status: { ...initialSensorStatus },
  },
  
  gnss: {
    latest: null,
    history: [],
    status: { ...initialSensorStatus },
  },
  
  updateCameraData: (camera: 'left' | 'right', data: CameraData) => set((state) => ({
    camera: {
      ...state.camera,
      [camera]: data,
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.camera.status.frequency,
        errorCount: state.camera.status.errorCount,
      },
    },
  })),
  
  updateLidarData: (data: LidarData) => set((state) => ({
    lidar: {
      latest: data,
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.lidar.status.frequency,
        errorCount: state.lidar.status.errorCount,
      },
    },
  })),
  
  updateGNSSData: (data: GNSSData) => set((state) => ({
    gnss: {
      latest: data,
      history: [...state.gnss.history.slice(-99), data], // 保留最近100条
      status: {
        connected: true,
        lastUpdate: Date.now(),
        frequency: state.gnss.status.frequency,
        errorCount: state.gnss.status.errorCount,
      },
    },
  })),
  
  updateSensorStatus: (sensor: 'camera' | 'lidar' | 'gnss', status: Partial<SensorStatus>) => set((state) => {
    if (sensor === 'camera') {
      return {
        camera: {
          ...state.camera,
          status: {
            ...state.camera.status,
            ...status,
          },
        },
      };
    } else if (sensor === 'lidar') {
      return {
        lidar: {
          ...state.lidar,
          status: {
            ...state.lidar.status,
            ...status,
          },
        },
      };
    } else if (sensor === 'gnss') {
      return {
        gnss: {
          ...state.gnss,
          status: {
            ...state.gnss.status,
            ...status,
          },
        },
      };
    }
    return state;
  }),
  
  clearGNSSData: () => set(() => ({
    gnss: {
      latest: null,
      history: [],
      status: { ...initialSensorStatus },
    },
  })),
  
  clearAllData: () => set(() => ({
    camera: {
      left: null,
      right: null,
      status: { ...initialSensorStatus },
    },
    lidar: {
      latest: null,
      status: { ...initialSensorStatus },
    },
    gnss: {
      latest: null,
      history: [],
      status: { ...initialSensorStatus },
    },
  })),
}));

