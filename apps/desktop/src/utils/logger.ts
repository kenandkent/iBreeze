type LogLevel = 'info' | 'warn' | 'error' | 'debug';

function log(level: LogLevel, module: string, action: string, ...args: unknown[]) {
  if (import.meta.env.PROD) return;
  const prefix = `[${module}] ${action}`;
  const data = args.length === 1 ? args[0] : args.length > 1 ? args : undefined;
  switch (level) {
    case 'error':
      console.error(prefix, data);
      break;
    case 'warn':
      console.warn(prefix, data);
      break;
    case 'debug':
      console.debug(prefix, data);
      break;
    default:
      console.info(prefix, data);
  }
}

export const logger = {
  info: (module: string, action: string, ...args: unknown[]) => log('info', module, action, ...args),
  warn: (module: string, action: string, ...args: unknown[]) => log('warn', module, action, ...args),
  error: (module: string, action: string, ...args: unknown[]) => log('error', module, action, ...args),
  debug: (module: string, action: string, ...args: unknown[]) => log('debug', module, action, ...args),
  logPageInit: (page: string) => log('info', page, 'init'),
  logPageLoad: (page: string, data?: unknown) => log('info', page, 'load', data),
  logPageError: (page: string, error: Error) => log('error', page, 'error', error.message),
  logHookSuccess: (hook: string, method: string, duration: number) => log('info', hook, `${method} ok`, `${duration.toFixed(0)}ms`),
  logHookError: (hook: string, method: string, error: Error, duration: number) => log('error', hook, `${method} fail`, `${duration.toFixed(0)}ms ${error.message}`),
  logAction: (page: string, action: string, data?: unknown) => log('info', page, action, data),
  logMenuClick: (key: string) => log('info', 'Layout', 'menu_click', key),
  logNavigation: (from: string, to: string) => log('info', 'Navigation', `${from} -> ${to}`),
};
