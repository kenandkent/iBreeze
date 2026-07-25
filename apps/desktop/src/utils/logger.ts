type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  module: string;
  action: string;
  data?: Record<string, unknown>;
  trace_id?: string;
  error?: string;
  stack?: string;
}

class Logger {
  private _traceId: string = '';
  private _buffer: LogEntry[] = [];
  private _flushInterval: ReturnType<typeof setInterval> | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      this._flushInterval = setInterval(() => this._flush(), 5000);
    }
  }

  setTraceId(traceId: string) {
    this._traceId = traceId;
  }

  getTraceId(): string {
    return this._traceId || this._generateTraceId();
  }

  private _generateTraceId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  debug(module: string, action: string, data?: Record<string, unknown>) {
    if (import.meta.env.DEV) {
      this._log('debug', module, action, data);
    }
  }

  info(module: string, action: string, data?: Record<string, unknown>) {
    this._log('info', module, action, data);
  }

  warn(module: string, action: string, data?: Record<string, unknown>) {
    this._log('warn', module, action, data);
  }

  error(module: string, action: string, error: Error | string, data?: Record<string, unknown>) {
    const errorStr = error instanceof Error ? error.message : error;
    const stack = error instanceof Error ? error.stack : undefined;
    this._log('error', module, action, { ...data, error: errorStr, stack });
  }

  logAction(page: string, action: string, data?: Record<string, unknown>) {
    this.info(`UI:${page}`, `click.${action}`, data);
  }

  logPageInit(page: string, data?: Record<string, unknown>) {
    this.info(`Page:${page}`, 'initialized', data);
  }

  logPageLoad(page: string, data?: Record<string, unknown>) {
    this.info(`Page:${page}`, 'data.loaded', data);
  }

  logPageError(page: string, error: Error | string, data?: Record<string, unknown>) {
    this.error(`Page:${page}`, 'data.load.failed', error, data);
  }

  logHookCall(hook: string, method: string, data?: Record<string, unknown>) {
    this.debug(`Hook:${hook}`, `rpc.${method}`, data);
  }

  logHookSuccess(hook: string, method: string, elapsedMs: number, data?: Record<string, unknown>) {
    this.info(`Hook:${hook}`, `rpc.${method}.success`, { elapsed_ms: elapsedMs, ...data });
  }

  logHookError(hook: string, method: string, error: Error | string, elapsedMs?: number) {
    this.error(`Hook:${hook}`, `rpc.${method}.failed`, error, { elapsed_ms: elapsedMs });
  }

  logNavigation(from: string, to: string) {
    this.info('Layout', 'navigate', { from, to });
  }

  logMenuClick(menuKey: string) {
    this.info('Layout', 'menu.click', { menu: menuKey });
  }

  private _log(level: LogLevel, module: string, action: string, data?: Record<string, unknown>) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      module,
      action,
      data,
      trace_id: this._traceId,
    };

    const prefix = `${entry.timestamp} [iBreeze] [${level.toUpperCase()}] [${module}] ${action}`;
    switch (level) {
      case 'debug': console.debug(prefix, data || '');
        break;
      case 'info': console.info(prefix, data || '');
        break;
      case 'warn': console.warn(prefix, data || '');
        break;
      case 'error': console.error(prefix, data || '');
        break;
    }

    this._buffer.push(entry);
    if (this._buffer.length >= 50) {
      this._flush();
    }
  }

  private async _flush() {
    if (this._buffer.length === 0) return;
    const entries = this._buffer.splice(0);
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('rpc_request', {
        method: 'event.subscribe',
        params: { scope: 'desktop_logs', entries },
      });
    } catch {
      // Silent fail — logging should never crash the app
    }
  }

  destroy() {
    if (this._flushInterval) {
      clearInterval(this._flushInterval);
    }
    this._flush();
  }
}

export const logger = new Logger();
export default logger;
