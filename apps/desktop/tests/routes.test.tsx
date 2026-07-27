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
});
