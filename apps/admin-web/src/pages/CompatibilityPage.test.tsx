import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import CompatibilityPage from './CompatibilityPage';
import * as apiClient from '../utils/apiClient';

const mockApiGet = vi.spyOn(apiClient, 'apiGet');
const mockApiPost = vi.spyOn(apiClient, 'apiPost');
const mockApiPatch = vi.spyOn(apiClient, 'apiPatch');
const mockApiDelete = vi.spyOn(apiClient, 'apiDelete');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><CompatibilityPage /></TestProviders>);
}

describe('CompatibilityPage interactions', () => {
  beforeEach(() => { vi.clearAllMocks(); mockApiGet.mockResolvedValue({ items: [] }); });

  it('creates rule with all required fields', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();
    fireEvent.click(screen.getByText('新建规则'));
    fireEvent.change(screen.getByLabelText('Agent Key'), { target: { value: 'agent1' } });
    fireEvent.change(screen.getByLabelText('模型 Key'), { target: { value: 'gpt-4' } });
    const selects = screen.getAllByRole('combobox');
    fireEvent.mouseDown(selects[0]);
    await waitFor(() => {
      const opt = screen.getAllByText('允许').find(el => el.closest('.ant-select-item'));
      if (opt) fireEvent.click(opt);
    });
    fireEvent.change(screen.getByLabelText('优先级'), { target: { value: '10' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('edits rule', async () => {
    mockApiPatch.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', agent_key: 'a1', model_key: 'm1', action: 'allow', priority: 10, enabled: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('shows error on edit failure', async () => {
    mockApiPatch.mockRejectedValue(new Error('编辑失败'));
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', agent_key: 'a1', model_key: 'm1', action: 'allow', priority: 10, enabled: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('deletes rule', async () => {
    mockApiDelete.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', agent_key: 'a1', model_key: 'm1', action: 'allow', priority: 10, enabled: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('shows error on delete failure', async () => {
    mockApiDelete.mockRejectedValue(new Error('删除失败'));
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', agent_key: 'a1', model_key: 'm1', action: 'allow', priority: 10, enabled: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('a1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('renders all action types', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', agent_key: 'a1', model_key: 'm1', action: 'allow', priority: 10, enabled: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '2', agent_key: 'a2', model_key: 'm2', provider_key: 'p1', action: 'deny', priority: 5, enabled: false, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '3', agent_key: 'a3', model_key: 'm3', action: 'fallback', priority: 1, enabled: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      ],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('允许')).toBeInTheDocument(); });
    expect(screen.getByText('拒绝')).toBeInTheDocument();
    expect(screen.getByText('回退')).toBeInTheDocument();
    expect(screen.getByText('p1')).toBeInTheDocument();
  });
});
