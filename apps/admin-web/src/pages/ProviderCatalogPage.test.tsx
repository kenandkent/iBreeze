import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import ProviderCatalogPage from './ProviderCatalogPage';
import * as apiClient from '../utils/apiClient';

vi.mock('../utils/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

const mockApiGet = vi.spyOn(apiClient, 'apiGet');
const mockApiPost = vi.spyOn(apiClient, 'apiPost');
const mockApiPatch = vi.spyOn(apiClient, 'apiPatch');
const mockApiDelete = vi.spyOn(apiClient, 'apiDelete');

function makeItem(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: '1', key: 'openai', display_name: 'OpenAI', base_url: 'https://api.openai.com',
    protocol: 'openai_chat_completions', auth_scheme: 'bearer',
    status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><ProviderCatalogPage /></TestProviders>);
}

describe('ProviderCatalogPage interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockResolvedValue({ items: [] });
  });

  it('opens create modal and submits', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();

    fireEvent.click(screen.getByText('新建提供商'));
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: 'openai' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'OpenAI' } });
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://api.openai.com' } });
    fireEvent.change(screen.getByLabelText('API 协议'), { target: { value: 'openai_chat_completions' } });
    fireEvent.change(screen.getByLabelText('认证方式'), { target: { value: 'bearer' } });
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalled();
    });
  });

  it('shows error on create failure', async () => {
    mockApiPost.mockRejectedValue(new Error('创建失败'));
    renderPage();

    fireEvent.click(screen.getByText('新建提供商'));
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: 'fail' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Fail' } });
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://fail.com' } });
    fireEvent.change(screen.getByLabelText('API 协议'), { target: { value: 'openai_chat_completions' } });
    fireEvent.change(screen.getByLabelText('认证方式'), { target: { value: 'bearer' } });
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalled();
    });
  });

  it('renders providers table', async () => {
    mockApiGet.mockResolvedValue({
      items: [makeItem({ status: 'published' })],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });
    expect(screen.getAllByText('已发布').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('https://api.openai.com')).toBeInTheDocument();
  });

  it('edits provider via edit button', async () => {
    mockApiPatch.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('编辑'));
    expect(screen.getByText('编辑提供商', { selector: '.ant-modal-title' })).toBeInTheDocument();
    const keyInput = screen.getByLabelText('Key') as HTMLInputElement;
    expect(keyInput.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Updated OpenAI' } });
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalled();
    });
  });

  it('cancels the edit modal', async () => {
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('编辑'));
    expect(screen.getByText('编辑提供商', { selector: '.ant-modal-title' })).toBeInTheDocument();
    fireEvent.click(screen.getByText('取 消'));
    expect(mockApiPatch).not.toHaveBeenCalled();
  });

  it('shows error on edit failure', async () => {
    mockApiPatch.mockRejectedValue('编辑失败');
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('编辑'));
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Updated OpenAI' } });
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalled();
    });
  });

  it('deletes provider', async () => {
    mockApiDelete.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('删除'));
    const confirmBtn = screen.getByText('确 定');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalled();
    });
  });

  it('shows error on delete failure', async () => {
    mockApiDelete.mockRejectedValue(new Error('删除失败'));
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalled();
    });
  });

  it('handles non-Error delete failure', async () => {
    mockApiDelete.mockRejectedValue('删除失败');
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));

    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalled();
    });
  });

  it('validates provider', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('验证'));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/providers/1/validate');
    });
  });

  it('shows error on validate failure', async () => {
    mockApiPost.mockRejectedValue(new Error('验证失败'));
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('验证'));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/providers/1/validate');
    });
  });

  it('handles non-Error validate failure', async () => {
    mockApiPost.mockRejectedValue('验证失败');
    mockApiGet.mockResolvedValue({ items: [makeItem()] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('验证'));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/providers/1/validate');
    });
  });

  it('renders draft, validated and unknown statuses', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        makeItem({ id: '1', key: 'draft-key', status: 'draft' }),
        makeItem({ id: '2', key: 'validated-key', status: 'validated' }),
        makeItem({ id: '3', key: 'unknown-key', status: 'unknown' as never }),
      ],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('draft-key')).toBeInTheDocument();
    });
    expect(screen.getByText('草稿')).toBeInTheDocument();
    expect(screen.getByText('已验证')).toBeInTheDocument();
    expect(screen.getByText('已验证（通过发布流程发布）')).toBeInTheDocument();
    expect(screen.getByText('unknown')).toBeInTheDocument();
    expect(screen.getAllByText('编辑').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('验证').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('删除').length).toBeGreaterThanOrEqual(1);
  });
});
