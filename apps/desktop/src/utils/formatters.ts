/**
 * Unified formatters for iBreeze Desktop
 * All times displayed in Asia/Shanghai (Beijing Time)
 * Numbers formatted to max 2 decimal places, no trailing zeros
 */

const BEIJING_TZ = 'Asia/Shanghai';

export function formatTime(dateStr: string | Date | undefined | null): string {
  if (!dateStr) return '-';
  try {
    const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    return date.toLocaleString('zh-CN', {
      timeZone: BEIJING_TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '-';
  }
}

export function formatDate(dateStr: string | Date | undefined | null): string {
  if (!dateStr) return '-';
  try {
    const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    return date.toLocaleDateString('zh-CN', {
      timeZone: BEIJING_TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return '-';
  }
}

export function formatNumber(value: number | undefined | null, maxDecimals: number = 2): string {
  if (value === undefined || value === null || isNaN(value)) return '-';
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: maxDecimals,
  });
}

export function formatBytes(bytes: number | undefined | null): string {
  if (bytes === undefined || bytes === null || isNaN(bytes)) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unitIndex = 0;
  let size = bytes;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${formatNumber(size)} ${units[unitIndex]}`;
}

export function formatDuration(seconds: number | undefined | null): string {
  if (seconds === undefined || seconds === null || isNaN(seconds)) return '-';
  if (seconds < 60) return `${formatNumber(seconds)}秒`;
  if (seconds < 3600) return `${formatNumber(seconds / 60)}分钟`;
  return `${formatNumber(seconds / 3600)}小时`;
}
