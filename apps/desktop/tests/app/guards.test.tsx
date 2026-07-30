import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { OriginGuard, AuthGuard, CompanyGuard } from '../../src/app/guards';
import { useAuthStore } from '../../src/stores/authStore';
import { useAppStore } from '../../src/stores/appStore';

describe('OriginGuard', () => {
  beforeEach(() => {
    useAuthStore.setState({ backendOrigin: null });
  });

  it('redirects when no backendOrigin', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/auth/server" element={<div>server page</div>} />
          <Route path="/test" element={<OriginGuard><div>child</div></OriginGuard>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(document.body.textContent).toContain('server page');
    expect(document.body.textContent).not.toContain('child');
    unmount();
  });

  it('renders children when backendOrigin is set', () => {
    useAuthStore.setState({ backendOrigin: 'https://test.com' });
    const { unmount } = render(
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/auth/server" element={<div>server page</div>} />
          <Route path="/test" element={<OriginGuard><div>child</div></OriginGuard>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(document.body.textContent).toContain('child');
    unmount();
  });
});

describe('AuthGuard', () => {
  beforeEach(() => {
    useAuthStore.setState({ profileOpened: false });
  });

  it('redirects when profileOpened is false', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/test" element={<AuthGuard><div>child</div></AuthGuard>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(document.body.textContent).toContain('login page');
    expect(document.body.textContent).not.toContain('child');
    unmount();
  });

  it('renders children when profileOpened is true', () => {
    useAuthStore.setState({ profileOpened: true });
    const { unmount } = render(
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/test" element={<AuthGuard><div>child</div></AuthGuard>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(document.body.textContent).toContain('child');
    unmount();
  });
});

describe('CompanyGuard', () => {
  beforeEach(() => {
    useAppStore.setState({ selectedCompanyId: null });
  });

  it('redirects when no selectedCompanyId', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/companies" element={<div>companies page</div>} />
          <Route path="/test" element={<CompanyGuard><div>child</div></CompanyGuard>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(document.body.textContent).toContain('companies page');
    expect(document.body.textContent).not.toContain('child');
    unmount();
  });

  it('renders children when selectedCompanyId is set', () => {
    useAppStore.setState({ selectedCompanyId: 'company-1' });
    const { unmount } = render(
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/companies" element={<div>companies page</div>} />
          <Route path="/test" element={<CompanyGuard><div>child</div></CompanyGuard>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(document.body.textContent).toContain('child');
    unmount();
  });
});
