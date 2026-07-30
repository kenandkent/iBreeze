import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import ModelCatalogPage from './ModelCatalogPage';
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
  return render(<TestProviders qc={qc}><ModelCatalogPage /></TestProviders>);
}

const draftModel = { id: '1', provider_key: 'openai', model_key: 'gpt-4', display_name: 'GPT-4', context_window: 8192, supports_tools: true, supports_streaming: true, supports_vision: false, status: 'draft', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' };

describe('ModelCatalogPage interactions', () => {
  beforeEach(() => { vi.clearAllMocks(); mockApiGet.mockResolvedValue({ items: [] }); });

  it('creates model', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();
    fireEvent.click(screen.getByText('新建模型'));
    fireEvent.change(screen.getByLabelText('提供商 Key'), { target: { value: 'openai' } });
    fireEvent.change(screen.getByLabelText('模型 Key'), { target: { value: 'gpt-4' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'GPT-4' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on create failure', async () => {
    mockApiPost.mockRejectedValue(new Error('创建失败'));
    renderPage();
    fireEvent.click(screen.getByText('新建模型'));
    fireEvent.change(screen.getByLabelText('提供商 Key'), { target: { value: 'openai' } });
    fireEvent.change(screen.getByLabelText('模型 Key'), { target: { value: 'gpt-4' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'GPT-4' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('edits model', async () => {
    mockApiPatch.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({ items: [draftModel] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('GPT-4')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    expect(screen.getByText('编辑模型')).toBeInTheDocument();
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('shows error on edit failure', async () => {
    mockApiPatch.mockRejectedValue(new Error('编辑失败'));
    mockApiGet.mockResolvedValue({ items: [draftModel] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('GPT-4')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('编辑'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPatch).toHaveBeenCalled(); });
  });

  it('validates model', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    mockApiGet.mockResolvedValue({ items: [draftModel] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('GPT-4')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('验证'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalledWith('/models/1/validate'); });
  });

  it('shows error on validate failure', async () => {
    mockApiPost.mockRejectedValue(new Error('验证失败'));
    mockApiGet.mockResolvedValue({ items: [draftModel] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('GPT-4')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('验证'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('deletes model', async () => {
    mockApiDelete.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({ items: [draftModel] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('GPT-4')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('shows error on delete failure', async () => {
    mockApiDelete.mockRejectedValue(new Error('删除失败'));
    mockApiGet.mockResolvedValue({ items: [draftModel] });
    renderPage();
    await waitFor(() => { expect(screen.getByText('GPT-4')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('删除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('renders table with all capabilities and statuses', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { ...draftModel, supports_tools: true, supports_streaming: true, supports_vision: true, status: 'draft' },
        { ...draftModel, id: '2', provider_key: 'anthropic', model_key: 'claude-3', display_name: 'Claude 3', supports_tools: false, supports_streaming: false, supports_vision: false, status: 'validated' },
        { ...draftModel, id: '3', provider_key: 'google', model_key: 'gemini', display_name: 'Gemini', status: 'published', context_window: undefined },
      ],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('anthropic')).toBeInTheDocument();
      expect(screen.getByText('Vision')).toBeInTheDocument();
    });
    expect(screen.getByText('已验证（通过发布流程发布）')).toBeInTheDocument();
    expect(screen.getAllByText('已发布').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.getAllByText('编辑').length).toBeGreaterThanOrEqual(1);
  });
});
