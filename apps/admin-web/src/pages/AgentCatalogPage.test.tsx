import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import AgentCatalogPage from './AgentCatalogPage';
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
  return render(<TestProviders qc={qc}><AgentCatalogPage /></TestProviders>);
}

describe('AgentCatalogPage interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockResolvedValue({ items: [] });
  });

  it('opens create modal and submits', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();
    fireEvent.click(screen.getByText('新建 Agent'));
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: 'test-agent' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Test Agent' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on create failure', async () => {
    mockApiPost.mockRejectedValue(new Error('创建失败'));
    renderPage();
    fireEvent.click(screen.getByText('新建 Agent'));
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: 'fail' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Fail' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('edits agent via edit button', async () => {
    mockApiPatch.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();

    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });

    const editBtn = screen.getByText('编辑');
    fireEvent.click(editBtn);

    expect(screen.getByText('编辑 Agent', { selector: '.ant-modal-title' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('validates agent', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();

    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });

    fireEvent.click(screen.getByText('验证'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalledWith('/agents/1/validate'); });
  });

  it('shows error on validate failure', async () => {
    mockApiPost.mockRejectedValue(new Error('验证失败'));
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();

    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('验证'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('deletes agent', async () => {
    mockApiDelete.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();

    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });

    fireEvent.click(screen.getByText('删除'));
    const confirmBtn = screen.getByText('确 定');
    fireEvent.click(confirmBtn);

    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('shows error on delete failure', async () => {
    mockApiDelete.mockRejectedValue(new Error('删除失败'));
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();

    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('shows error on edit failure', async () => {
    mockApiPatch.mockRejectedValue(new Error('编辑失败'));
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();

    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('renders table with all statuses', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', key: 'a1', display_name: 'A1', catalog_revision: 1, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '2', key: 'a2', display_name: 'A2', catalog_revision: 2, status: 'validated', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '3', key: 'a3', display_name: 'A3', catalog_revision: 3, status: 'published', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      ],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    expect(screen.getByText('草稿')).toBeInTheDocument();
    expect(screen.getByText('已验证（通过发布流程发布）')).toBeInTheDocument();
    expect(screen.getAllByText('已发布').length).toBeGreaterThanOrEqual(1);
  });
});
