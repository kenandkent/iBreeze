import { describe, it, expect } from 'vitest';
import { formatTime, formatDate, formatNumber, formatBytes, formatDuration } from './formatters';

describe('formatTime', () => {
  it('returns "-" for null/undefined', () => {
    expect(formatTime(null)).toBe('-');
    expect(formatTime(undefined)).toBe('-');
  });

  it('formats a valid ISO string', () => {
    const result = formatTime('2024-06-15T10:30:00Z');
    expect(result).toContain('2024');
    expect(result).toContain('06');
    expect(result).toContain('15');
  });

  it('formats a Date object', () => {
    const result = formatTime(new Date('2024-06-15T10:30:00Z'));
    expect(result).toContain('2024');
  });
});

describe('formatDate', () => {
  it('returns "-" for null/undefined', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate(undefined)).toBe('-');
  });

  it('formats a date string', () => {
    const result = formatDate('2024-06-15T10:30:00Z');
    expect(result).toContain('2024');
    expect(result).toContain('06');
    expect(result).toContain('15');
  });
});

describe('formatNumber', () => {
  it('returns "-" for null/undefined/NaN', () => {
    expect(formatNumber(null)).toBe('-');
    expect(formatNumber(undefined)).toBe('-');
    expect(formatNumber(NaN)).toBe('-');
  });

  it('formats integer', () => {
    expect(formatNumber(42)).toBe('42');
  });

  it('respects maxDecimals', () => {
    expect(formatNumber(3.14159, 2)).toBe('3.14');
  });
});

describe('formatBytes', () => {
  it('returns "-" for null/undefined/NaN', () => {
    expect(formatBytes(null)).toBe('-');
    expect(formatBytes(undefined)).toBe('-');
    expect(formatBytes(NaN)).toBe('-');
  });

  it('formats bytes', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('formats KB', () => {
    expect(formatBytes(1024)).toBe('1 KB');
  });

  it('formats MB', () => {
    expect(formatBytes(1048576)).toBe('1 MB');
  });
});

describe('formatDuration', () => {
  it('returns "-" for null/undefined/NaN', () => {
    expect(formatDuration(null)).toBe('-');
    expect(formatDuration(undefined)).toBe('-');
    expect(formatDuration(NaN)).toBe('-');
  });

  it('formats seconds', () => {
    expect(formatDuration(30)).toBe('30秒');
  });

  it('formats minutes', () => {
    expect(formatDuration(120)).toBe('2分钟');
  });

  it('formats hours', () => {
    expect(formatDuration(7200)).toBe('2小时');
  });
});
