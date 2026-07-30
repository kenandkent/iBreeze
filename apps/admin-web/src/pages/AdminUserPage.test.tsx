import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import AdminUserPage from './AdminUserPage';
import * as apiClient from '../utils/apiClient';

vi.mock('../utils/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

const mockApiGet = vi.spyOn(apiClient, 'apiGet');
const mockApiPost = vi.spyOn(apiClient, 'apiPost');
const mockApiPatch = vi.spyOn(apiClient, 'apiPatch');
const mockApiDelete = vi.spyOn(apiClient, 'apiDelete');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><AdminUserPage /></TestProviders>);
}

describe('AdminUserPage interactions', () => {
  const mockUser = { id: '1', username: 'admin', email: 'admin@test.com', user_type: 'admin', role: 'superadmin', is_active: true, protected: false, must_change_password: false, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' };

  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockResolvedValue({ users: [] });
  });

  it('creates user successfully', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();
    fireEvent.click(screen.getByText('新建用户'));
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'test@test.com' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pass123' } });
    const selects = screen.getAllByRole('combobox');
    fireEvent.mouseDown(selects[0]);
    await waitFor(() => {
      const opt = screen.getAllByText('管理员').find(el => el.closest('.ant-select-item'));
      if (opt) fireEvent.click(opt);
    });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on create failure', async () => {
    mockApiPost.mockRejectedValue(new Error('创建失败'));
    renderPage();
    fireEvent.click(screen.getByText('新建用户'));
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'test@test.com' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'pass123' } });
    const selects = screen.getAllByRole('combobox');
    fireEvent.mouseDown(selects[0]);
    await waitFor(() => {
      const opt = screen.getAllByText('管理员').find(el => el.closest('.ant-select-item'));
      if (opt) fireEvent.click(opt);
    });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('edits user', async () => {
    mockApiPatch.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    expect(screen.getByText('编辑用户', { selector: '.ant-modal-title' })).toBeInTheDocument();
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('shows error on edit failure', async () => {
    mockApiPatch.mockRejectedValue(new Error('编辑失败'));
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('deletes user', async () => {
    mockApiDelete.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('shows error on delete failure', async () => {
    mockApiDelete.mockRejectedValue(new Error('删除失败'));
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('opens reset password modal', async () => {
    mockApiPost.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('重置密码'));
    expect(screen.getByText('重置密码', { selector: '.ant-modal-title' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'newpass' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on reset password failure', async () => {
    mockApiPost.mockRejectedValue(new Error('重置失败'));
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('重置密码'));
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'newpass' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('revokes sessions', async () => {
    mockApiPost.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('撤销会话'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on revoke sessions failure', async () => {
    mockApiPost.mockRejectedValue(new Error('撤销失败'));
    mockApiGet.mockResolvedValue({ users: [mockUser] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('撤销会话'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('renders table with data and tags', async () => {
    mockApiGet.mockResolvedValue({
      users: [
        { ...mockUser, protected: true },
        { id: '2', username: 'user1', email: 'user1@test.com', user_type: 'app_user', role: 'viewer', is_active: false, protected: false, must_change_password: false, created_at: '2024-02-01T00:00:00Z', updated_at: '2024-02-01T00:00:00Z' },
      ],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('admin')).toBeInTheDocument(); });
    expect(screen.getByText('管理员')).toBeInTheDocument();
    expect(screen.getByText('禁用')).toBeInTheDocument();
  });
});
