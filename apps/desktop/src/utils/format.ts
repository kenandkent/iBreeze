const BJ_TIMEZONE = 'Asia/Shanghai';

export function formatBJTime(value: string | undefined | null): string {
  if (!value) return '-';
  let date: Date;
  if (value.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(value)) {
    date = new Date(value);
  } else {
    date = new Date(`${value}Z`);
  }
  if (isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BJ_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatNumber(value: number | undefined | null): string {
  if (value === undefined || value === null || isNaN(value)) return '-';
  return Number(value.toFixed(2)).toString();
}

export function formatMicros(micros: number | undefined | null): string {
  if (micros === undefined || micros === null || isNaN(micros)) return '-';
  return formatNumber(micros / 1_000_000);
}
