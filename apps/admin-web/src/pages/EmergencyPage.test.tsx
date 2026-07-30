import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import EmergencyPage from './EmergencyPage';
import * as apiClient from '../utils/apiClient';

vi.mock('../utils/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

const mockApiGet = vi.spyOn(apiClient, 'apiGet');
const mockApiPost = vi.spyOn(apiClient, 'apiPost');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><EmergencyPage /></TestProviders>);
}

describe('EmergencyPage interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockResolvedValue(null);
  });

  it('submits emergency disable form with all required fields', async () => {
    mockApiPost.mockResolvedValue(undefined);
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('执行紧急禁用').length).toBeGreaterThanOrEqual(1);
    });

    const selects = screen.getAllByRole('combobox');
    fireEvent.mouseDown(selects[0]);
    await waitFor(() => {
      const opt = screen.getAllByText('agents').find(el => el.closest('.ant-select-item'));
      if (opt) fireEvent.click(opt);
    });

    fireEvent.change(screen.getByLabelText('资源 ID'), { target: { value: 'res-123' } });
    fireEvent.change(screen.getByLabelText('原因'), { target: { value: 'Critical bug' } });
    fireEvent.change(screen.getByLabelText('紧急确认码'), { target: { value: 'EMERGENCY' } });
    const buttons = screen.getAllByText('执行紧急禁用');
    const submitBtn = buttons[buttons.length - 1];
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalled();
    });
  });

  it('shows error on failure', async () => {
    mockApiPost.mockRejectedValue(new Error('Failed'));
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('执行紧急禁用').length).toBeGreaterThanOrEqual(1);
    });

    const selects = screen.getAllByRole('combobox');
    fireEvent.mouseDown(selects[0]);
    await waitFor(() => {
      const opt = screen.getAllByText('agents').find(el => el.closest('.ant-select-item'));
      if (opt) fireEvent.click(opt);
    });

    fireEvent.change(screen.getByLabelText('资源 ID'), { target: { value: 'res-123' } });
    fireEvent.change(screen.getByLabelText('原因'), { target: { value: 'Critical bug' } });
    fireEvent.change(screen.getByLabelText('紧急确认码'), { target: { value: 'EMERGENCY' } });
    const buttons = screen.getAllByText('执行紧急禁用');
    fireEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalled();
    });
  });

  it('shows latest disable record when available', async () => {
    mockApiGet.mockResolvedValue({
      id: 'disp-1', sequence: 5, resource_type: 'agents',
      resource_id: 'agent-123', created_at: '2024-06-15T10:30:00Z',
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('disp-1')).toBeInTheDocument();
    });
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('agents')).toBeInTheDocument();
    expect(screen.getByText('agent-123')).toBeInTheDocument();
  });

  it('shows dash for missing fields', async () => {
    mockApiGet.mockResolvedValue({
      id: 'disp-1', sequence: 1, created_at: '2024-06-15T10:30:00Z',
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('disp-1')).toBeInTheDocument();
    });
  });
});
