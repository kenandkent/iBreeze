import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import Layout from './Layout';

vi.mock('../stores/authStore');
vi.mock('../utils/apiClient', () => ({
  apiLogout: vi.fn().mockResolvedValue(undefined),
}));

describe('Layout', () => {
  const mockLogout = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuthStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      return selector({
        token: 'test-token',
        isAuthenticated: true,
        logout: mockLogout,
      }) as never;
    });
  });

  it('renders the admin title and menu items', () => {
    render(
      <MemoryRouter initialEntries={['/agents']}>
        <Layout />
      </MemoryRouter>,
    );
    expect(screen.getByText('iBreeze Admin')).toBeInTheDocument();
    expect(screen.getByText('Agent 管理')).toBeInTheDocument();
    expect(screen.getByText('模型管理')).toBeInTheDocument();
    expect(screen.getByText('用户管理')).toBeInTheDocument();
  });

  it('handles logout click', async () => {
    const { apiLogout } = await import('../utils/apiClient');
    render(
      <MemoryRouter initialEntries={['/agents']}>
        <Layout />
      </MemoryRouter>,
    );

    const logoutBtn = screen.getByRole('img', { name: /logout/i });
    fireEvent.click(logoutBtn);

    await waitFor(() => {
      expect(apiLogout).toHaveBeenCalled();
      expect(mockLogout).toHaveBeenCalled();
    });
  });

  it('handles menu navigation', () => {
    render(
      <MemoryRouter initialEntries={['/agents']}>
        <Layout />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText('用户管理'));
    fireEvent.click(screen.getByText('系统设置'));
    fireEvent.click(screen.getByText('审计日志'));
  });
});
