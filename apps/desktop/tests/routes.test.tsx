import { describe, it, expect } from 'vitest';
import { routes } from '../src/app/routes';
import type { RouteObject } from 'react-router-dom';

function collectPaths(routeList: RouteObject[], parentPath = ''): string[] {
  const paths: string[] = [];
  for (const route of routeList) {
    const segment = route.path ?? '';
    const fullPath = route.index
      ? parentPath || '/'
      : parentPath.endsWith('/') || segment.startsWith('/')
        ? `${parentPath}${segment}`
        : `${parentPath}/${segment}`;
    if (route.path || route.index) {
      paths.push(fullPath || '/');
    }
    if (route.children) {
      paths.push(...collectPaths(route.children, fullPath));
    }
  }
  return paths;
}

describe('routes structure', () => {
  it('has auth routes accessible without guard', () => {
    const authPaths = [
      '/auth/server',
      '/login',
      '/register',
      '/auth/change-password',
      '/offline-unlock',
    ];
    const allPaths = collectPaths(routes);
    for (const p of authPaths) {
      expect(allPaths).toContain(p);
    }
  });

  it('has recovery route', () => {
    const allPaths = collectPaths(routes);
    expect(allPaths).toContain('/recovery');
  });

  it('has company-scoped routes', () => {
    const allPaths = collectPaths(routes);
    expect(allPaths).toContain('/companies/:companyId/departments');
    expect(allPaths).toContain('/companies/:companyId/employees');
    expect(allPaths).toContain('/companies/:companyId/tasks');
    expect(allPaths).toContain('/companies/:companyId/tasks/:taskId');
    expect(allPaths).toContain('/companies/:companyId/conversations');
    expect(allPaths).toContain('/companies/:companyId/knowledge');
    expect(allPaths).toContain('/companies/:companyId/workspaces');
    expect(allPaths).toContain('/companies/:companyId/orchestrations');
    expect(allPaths).toContain('/companies/:companyId/agents');
    expect(allPaths).toContain('/companies/:companyId/reviews');
  });

  it('has flat legacy routes (global scope only)', () => {
    const allPaths = collectPaths(routes);
    expect(allPaths).toContain('/dashboard');
    expect(allPaths).toContain('/companies');
    expect(allPaths).toContain('/settings');
    expect(allPaths).toContain('/diagnostics');
    expect(allPaths).toContain('/backups');
  });

  it('has company routes nested under the main layout', () => {
    const main = routes.find((r) => r.path === '/');
    expect(main).toBeDefined();
    const childPaths = main!.children?.map((c) => c.path).filter(Boolean) ?? [];
    expect(childPaths).toContain('companies');
  });

  it('auth routes are at top level, not under main layout', () => {
    const main = routes.find((r) => r.path === '/');
    const mainChildPaths = main?.children?.map((c) => c.path).filter(Boolean) ?? [];
    expect(mainChildPaths).not.toContain('auth/server');
    expect(mainChildPaths).not.toContain('login');
    expect(mainChildPaths).not.toContain('register');
  });

  it('auth routes appear first before main layout', () => {
    const authRouteIdx = routes.findIndex((r) => r.path === '/auth/server');
    const loginRouteIdx = routes.findIndex((r) => r.path === '/login');
    const mainRouteIdx = routes.findIndex((r) => r.path === '/');
    expect(authRouteIdx).toBeLessThan(mainRouteIdx);
    expect(loginRouteIdx).toBeLessThan(mainRouteIdx);
  });

  it('routes array has expected length', () => {
    expect(routes.length).toBeGreaterThanOrEqual(8);
  });

  it('auth/server route has element', () => {
    const route = routes.find((r) => r.path === '/auth/server');
    expect(route?.element).toBeDefined();
  });

  it('login route has element', () => {
    const route = routes.find((r) => r.path === '/login');
    expect(route?.element).toBeDefined();
  });

  it('main layout route has children', () => {
    const main = routes.find((r) => r.path === '/');
    expect(main?.children).toBeDefined();
    expect(main?.children!.length).toBeGreaterThan(0);
  });

  it('company route has children', () => {
    const companyRoute = routes.find((r) => r.path === '/companies/:companyId');
    expect(companyRoute?.children).toBeDefined();
    expect(companyRoute?.children!.length).toBeGreaterThan(0);
  });

  it('recovery route has element', () => {
    const route = routes.find((r) => r.path === '/recovery');
    expect(route?.element).toBeDefined();
  });

  it('main layout uses OriginGuard and AuthGuard', () => {
    const main = routes.find((r) => r.path === '/');
    expect(main?.element).toBeDefined();
  });

  it('company route uses guards', () => {
    const companyRoute = routes.find((r) => r.path === '/companies/:companyId');
    expect(companyRoute?.element).toBeDefined();
  });

  it('has all expected company child paths', () => {
    const companyRoute = routes.find((r) => r.path === '/companies/:companyId');
    const childPaths = companyRoute?.children?.map((c) => c.path).filter(Boolean) ?? [];
    const expected = [
      'dashboard', 'departments', 'employees', 'tasks',
      'conversations', 'knowledge', 'workspaces', 'orchestrations',
      'agents', 'reviews', 'audit-logs', 'settings', 'diagnostics',
      'skills', 'backups', 'approvals',
    ];
    for (const p of expected) {
      expect(childPaths).toContain(p);
    }
  });

  it('has all expected main child paths', () => {
    const main = routes.find((r) => r.path === '/');
    const childPaths = main?.children?.map((c) => c.path).filter(Boolean) ?? [];
    const expected = ['companies', 'dashboard', 'settings', 'diagnostics', 'backups'];
    for (const p of expected) {
      expect(childPaths).toContain(p);
    }
  });

  it('all route elements are defined', () => {
    for (const route of routes) {
      expect(route.element).toBeDefined();
    }
    const main = routes.find((r) => r.path === '/');
    for (const child of main?.children ?? []) {
      expect(child.element).toBeDefined();
    }
    const company = routes.find((r) => r.path === '/companies/:companyId');
    for (const child of company?.children ?? []) {
      expect(child.element).toBeDefined();
    }
  });

  it('has settings route under both main and company', () => {
    const allPaths = collectPaths(routes);
    expect(allPaths).toContain('/settings');
    expect(allPaths).toContain('/companies/:companyId/settings');
  });

  it('has diagnostics route under both main and company', () => {
    const allPaths = collectPaths(routes);
    expect(allPaths).toContain('/diagnostics');
    expect(allPaths).toContain('/companies/:companyId/diagnostics');
  });

  it('has backups route under both main and company', () => {
    const allPaths = collectPaths(routes);
    expect(allPaths).toContain('/backups');
    expect(allPaths).toContain('/companies/:companyId/backups');
  });
});
