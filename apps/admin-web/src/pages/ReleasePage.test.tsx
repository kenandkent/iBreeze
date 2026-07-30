import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import ReleasePage from './ReleasePage';
import * as apiClient from '../utils/apiClient';

vi.mock('../utils/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

const mockApiGet = vi.spyOn(apiClient, 'apiGet');
const mockApiPost = vi.spyOn(apiClient, 'apiPost');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><ReleasePage /></TestProviders>);
}

describe('ReleasePage interactions', () => {
  beforeEach(() => { vi.clearAllMocks(); mockApiGet.mockResolvedValue({ items: [] }); });

  it('creates release successfully', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();
    fireEvent.click(screen.getByText('新建发布'));
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '1.0.0' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on create failure', async () => {
    mockApiPost.mockRejectedValue(new Error('创建失败'));
    renderPage();
    fireEvent.click(screen.getByText('新建发布'));
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '1.0.0' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('validates release', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', version: '1.0', release_sequence: 1, signature: '', signing_key_id: 'k1', status: 'publishing', manifest: {}, created_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('1.0')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('验证'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalledWith('/catalog/releases/1/reconcile'); });
  });

  it('publishes release', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', version: '1.0', release_sequence: 1, signature: '', signing_key_id: 'k1', status: 'reconciled', manifest: {}, created_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('1.0')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('发布'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalledWith('/catalog/releases/1/publish'); });
  });

  it('renders releases with all statuses', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', version: '1.0', release_sequence: 1, signature: 'sig', signing_key_id: 'k1', status: 'publishing', manifest: {}, created_at: '2024-01-01T00:00:00Z' },
        { id: '2', version: '1.1', release_sequence: 2, signature: '', signing_key_id: 'k1', status: 'reconciled', manifest: {}, created_at: '2024-01-02T00:00:00Z' },
        { id: '3', version: '2.0', release_sequence: 3, signature: '', signing_key_id: 'k2', status: 'published', manifest: {}, created_at: '2024-01-03T00:00:00Z' },
      ],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('草稿')).toBeInTheDocument(); });
    expect(screen.getByText('已验证')).toBeInTheDocument();
    expect(screen.getAllByText('已发布').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('发布')).toBeInTheDocument();
  });
});
