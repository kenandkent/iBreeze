import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TestProviders } from '../test-utils';
import LoginPage from './LoginPage';
import { useAuthStore } from '../stores/authStore';

vi.mock('../stores/authStore');
vi.mock('../utils/apiClient');
vi.mock('../utils/deviceId', () => ({
  getDeviceId: vi.fn().mockReturnValue('mock-device-id'),
}));

import { apiLogin } from '../utils/apiClient';
const mockApiLogin = vi.mocked(apiLogin);

describe('LoginPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders login form', () => {
    vi.mocked(useAuthStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      return selector({ login: vi.fn() }) as never;
    });
    render(
      <MemoryRouter>
        <TestProviders>
          <LoginPage />
        </TestProviders>
      </MemoryRouter>,
    );
    expect(screen.getByText('iBreeze 管理后台')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('用户名/邮箱/手机')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('密码')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /登/ })).toBeInTheDocument();
  });

  it('successful login navigates to /agents', async () => {
    const mockLogin = vi.fn();
    vi.mocked(useAuthStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      return selector({ login: mockLogin }) as never;
    });
    mockApiLogin.mockResolvedValue({
      access_token: 'test-token',
      user: { username: 'admin', email: 'admin@test.com' },
      pwd_change_required: false,
    } as never);

    render(
      <MemoryRouter>
        <TestProviders>
          <LoginPage />
        </TestProviders>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText('用户名/邮箱/手机'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /登/ }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalled();
    });
  });

  it('shows error on login failure', async () => {
    vi.mocked(useAuthStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      return selector({ login: vi.fn() }) as never;
    });
    mockApiLogin.mockRejectedValue(new Error('用户名或密码错误'));

    render(
      <MemoryRouter>
        <TestProviders>
          <LoginPage />
        </TestProviders>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText('用户名/邮箱/手机'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: /登/ }));

    await waitFor(() => {
      expect(screen.getByText('用户名或密码错误')).toBeInTheDocument();
    });
  });

  it('shows generic error for non-Error exception', async () => {
    vi.mocked(useAuthStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      return selector({ login: vi.fn() }) as never;
    });
    mockApiLogin.mockRejectedValue('string error');

    render(
      <MemoryRouter>
        <TestProviders>
          <LoginPage />
        </TestProviders>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText('用户名/邮箱/手机'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /登/ }));

    await waitFor(() => {
      expect(screen.getByText('用户名或密码错误')).toBeInTheDocument();
    });
  });

  it('shows pwd_change_required from session response', async () => {
    const mockLogin = vi.fn();
    vi.mocked(useAuthStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      return selector({ login: mockLogin }) as never;
    });
    mockApiLogin.mockResolvedValue({
      access_token: 'test-token',
      user: { username: 'admin' },
      pwd_change_required: true,
    } as never);

    render(
      <MemoryRouter>
        <TestProviders>
          <LoginPage />
        </TestProviders>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText('用户名/邮箱/手机'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: 'pass' } });
    fireEvent.click(screen.getByRole('button', { name: /登/ }));

    await waitFor(() => {
      expect(screen.getByText('首次登录需要修改密码')).toBeInTheDocument();
    });
  });
});
