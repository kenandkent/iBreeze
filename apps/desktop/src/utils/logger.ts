const PREFIX = '[iBreeze]';

function fmt(level: string, module: string, action: string, data?: unknown): string {
  const ts = new Date().toISOString();
  const extra = data !== undefined ? ` ${JSON.stringify(data)}` : '';
  return `${ts} ${PREFIX} [${level}] [${module}] ${action}${extra}`;
}

function isDev(): boolean {
  try {
    return import.meta.env.DEV === true;
  } catch {
    return false;
  }
}

export const logger = {
  debug: (module: string, action: string, data?: Record<string, unknown>) => {
    if (isDev()) console.debug(fmt('DEBUG', module, action, data));
  },
  info: (module: string, action: string, data?: Record<string, unknown>) => {
    console.info(fmt('INFO', module, action, data));
  },
  warn: (module: string, action: string, data?: Record<string, unknown>) => {
    console.warn(fmt('WARN', module, action, data));
  },
  error: (module: string, action: string, data?: Record<string, unknown>, error?: unknown) => {
    console.error(fmt('ERROR', module, action, { ...data, error: String(error ?? '') }));
  },
};