// 统一调试日志工具 — 生产环境关闭，开发环境可通过 localStorage 开启

const DEBUG_KEY = 'ros_monitor_debug';

/** 检查是否启用调试日志 */
export const isDebugEnabled = (): boolean => {
  try {
    if (typeof localStorage === 'undefined') return false;
    return localStorage.getItem(DEBUG_KEY) === '1';
  } catch {
    return false;
  }
};

/** 调试日志，仅在 localStorage.ros_monitor_debug=1 时输出 */
export const debugLog = (...args: unknown[]): void => {
  if (isDebugEnabled()) {
    console.log('[DEBUG]', ...args);
  }
};

/** 警告日志（始终输出） */
export const warnLog = console.warn.bind(console);

/** 错误日志（始终输出） */
export const errorLog = console.error.bind(console);
