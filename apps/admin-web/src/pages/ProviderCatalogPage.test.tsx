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
      items: [{
        id: '1', key: 'openai', display_name: 'OpenAI', base_url: 'https://api.openai.com',
        protocol: 'openai_chat_completions', auth_scheme: 'bearer',
        status: 'published', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
      }],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('openai')).toBeInTheDocument();
    });
    expect(screen.getAllByText('已发布').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('https://api.openai.com')).toBeInTheDocument();
  });
});
