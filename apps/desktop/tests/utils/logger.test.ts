import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { logger } from '../../src/utils/logger';

describe('logger', () => {
  let infoSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;
  let debugSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('info calls console.info with prefix', () => {
    logger.info('Module', 'action');
    expect(infoSpy).toHaveBeenCalledWith('[Module] action', undefined);
  });

  it('info passes data argument', () => {
    logger.info('Module', 'action', { key: 'value' });
    expect(infoSpy).toHaveBeenCalledWith('[Module] action', { key: 'value' });
  });

  it('warn calls console.warn', () => {
    logger.warn('Module', 'warn_action');
    expect(warnSpy).toHaveBeenCalledWith('[Module] warn_action', undefined);
  });

  it('error calls console.error', () => {
    logger.error('Module', 'error_action');
    expect(errorSpy).toHaveBeenCalledWith('[Module] error_action', undefined);
  });

  it('debug calls console.debug', () => {
    logger.debug('Module', 'debug_action');
    expect(debugSpy).toHaveBeenCalledWith('[Module] debug_action', undefined);
  });

  it('logPageInit calls info with page init', () => {
    logger.logPageInit('TestPage');
    expect(infoSpy).toHaveBeenCalledWith('[TestPage] init', undefined);
  });

  it('logPageLoad calls info with page load', () => {
    logger.logPageLoad('TestPage', { data: 1 });
    expect(infoSpy).toHaveBeenCalledWith('[TestPage] load', { data: 1 });
  });

  it('logPageLoad without data', () => {
    logger.logPageLoad('TestPage');
    expect(infoSpy).toHaveBeenCalledWith('[TestPage] load', undefined);
  });

  it('logPageError calls error', () => {
    logger.logPageError('TestPage', new Error('test error'));
    expect(errorSpy).toHaveBeenCalledWith('[TestPage] error', 'test error');
  });

  it('logHookSuccess calls info with duration', () => {
    logger.logHookSuccess('useHook', 'method', 123.456);
    expect(infoSpy).toHaveBeenCalledWith('[useHook] method ok', '123ms');
  });

  it('logHookError calls error with duration and message', () => {
    logger.logHookError('useHook', 'method', new Error('fail'), 50.1);
    expect(errorSpy).toHaveBeenCalledWith('[useHook] method fail', '50ms fail');
  });

  it('logAction calls info', () => {
    logger.logAction('Page', 'click', { id: 1 });
    expect(infoSpy).toHaveBeenCalledWith('[Page] click', { id: 1 });
  });

  it('logMenuClick calls info', () => {
    logger.logMenuClick('/dashboard');
    expect(infoSpy).toHaveBeenCalledWith('[Layout] menu_click', '/dashboard');
  });

  it('logNavigation calls info', () => {
    logger.logNavigation('/from', '/to');
    expect(infoSpy).toHaveBeenCalledWith('[Navigation] /from -> /to', undefined);
  });
});

describe('logger in PROD mode', () => {
  let infoSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;
  let debugSpy: ReturnType<typeof vi.spyOn>;
  let originalProd: boolean;

  beforeEach(() => {
    originalProd = (import.meta as Record<string, unknown>).env
      ? ((import.meta.env as Record<string, unknown>).PROD as boolean)
      : false;
    vi.stubEnv('PROD', true);
    infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.stubEnv('PROD', originalProd);
    vi.restoreAllMocks();
  });

  it('does not log in PROD mode', () => {
    logger.info('Module', 'action');
    logger.warn('Module', 'action');
    logger.error('Module', 'action');
    logger.debug('Module', 'action');
    expect(infoSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
    expect(debugSpy).not.toHaveBeenCalled();
  });
});
