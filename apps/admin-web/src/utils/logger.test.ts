import { describe, it, expect, vi, beforeEach } from 'vitest';
import { logger } from './logger';

describe('logger', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('info calls console.info with formatted message', () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('TestModule', 'test_action', { key: 'value' });
    expect(spy).toHaveBeenCalledOnce();
    const msg = spy.mock.calls[0][0] as string;
    expect(msg).toContain('[iBreeze]');
    expect(msg).toContain('[INFO]');
    expect(msg).toContain('[TestModule]');
    expect(msg).toContain('test_action');
    expect(msg).toContain('key');
  });

  it('warn calls console.warn with formatted message', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    logger.warn('TestModule', 'warn_action');
    expect(spy).toHaveBeenCalledOnce();
    const msg = spy.mock.calls[0][0] as string;
    expect(msg).toContain('[WARN]');
  });

  it('error calls console.error with formatted message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    logger.error('TestModule', 'error_action', { detail: 'bad' }, new Error('boom'));
    expect(spy).toHaveBeenCalledOnce();
    const msg = spy.mock.calls[0][0] as string;
    expect(msg).toContain('[ERROR]');
    expect(msg).toContain('boom');
  });

  it('debug calls console.debug only in dev mode', () => {
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    logger.debug('TestModule', 'debug_action');
    if (import.meta.env.DEV) {
      expect(spy).toHaveBeenCalledOnce();
    } else {
      expect(spy).not.toHaveBeenCalled();
    }
  });

  it('info works without data parameter', () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('Mod', 'action');
    expect(spy).toHaveBeenCalledOnce();
    const msg = spy.mock.calls[0][0] as string;
    expect(msg).not.toContain('undefined');
  });
});
