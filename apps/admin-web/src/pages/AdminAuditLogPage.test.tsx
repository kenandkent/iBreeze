import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import AdminAuditLogPage from './AdminAuditLogPage';
import * as apiClient from '../utils/apiClient';

const mockApiGet = vi.spyOn(apiClient, 'apiGet');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><AdminAuditLogPage /></TestProviders>);
}

describe('AdminAuditLogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn().mockReturnValue('blob:mock'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  it('renders page with data', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', event_type: 'auth.login', actor_id: 'u1', resource_type: 'session', resource_id: 's1', detail: { ip: '127.0.0.1' }, created_at: '2024-01-01T00:00:00Z' },
        { id: '2', event_type: 'user.create', actor_id: 'u2', resource_type: 'user', resource_id: 'u2', detail: {}, created_at: '2024-01-02T00:00:00Z' },
        { id: '3', event_type: 'catalog.release.publish', actor_id: 'u3', resource_type: 'release', resource_id: 'r1', detail: { v: '1.0.0' }, created_at: '2024-01-03T00:00:00Z' },
      ],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('auth.login')).toBeInTheDocument();
    });
    expect(screen.getByText('user.create')).toBeInTheDocument();
    expect(screen.getByText('catalog.release.publish')).toBeInTheDocument();
    expect(screen.getByText('u1')).toBeInTheDocument();
    expect(screen.getByText('{"ip":"127.0.0.1"}')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });
  });

  it('exports CSV when clicking the export button', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', event_type: 'auth.login', actor_id: 'u1', resource_type: 'session', resource_id: 's1', detail: { ip: '127.0.0.1' }, created_at: '2024-01-01T00:00:00Z' },
      ],
    });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('auth.login')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /导出 CSV/ }));

    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);

    clickSpy.mockRestore();
  });

  it('refetches with event_type when a Select option is chosen', async () => {
    mockApiGet.mockResolvedValue({ items: [] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });

    const callsBefore = mockApiGet.mock.calls.length;
    fireEvent.mouseDown(screen.getByRole('combobox'));

    await waitFor(() => {
      expect(document.querySelectorAll('.ant-select-item-option').length).toBeGreaterThan(0);
    });

    const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find(
      (el) => el.textContent === 'auth.login',
    )!;
    fireEvent.mouseDown(option);
    fireEvent.click(option);

    await waitFor(() => {
      expect(mockApiGet.mock.calls.length).toBeGreaterThan(callsBefore);
    });
    const url = mockApiGet.mock.calls[mockApiGet.mock.calls.length - 1][0] as string;
    expect(url).toContain('/audit-logs?event_type=auth.login');
  });

  it('refetches with actor_id when the operator input changes, and drops it when cleared', async () => {
    mockApiGet.mockResolvedValue({ items: [] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('操作者 ID');

    const callsBefore = mockApiGet.mock.calls.length;
    fireEvent.change(input, { target: { value: 'u9' } });
    await waitFor(() => {
      expect(mockApiGet.mock.calls.length).toBeGreaterThan(callsBefore);
    });
    const url = mockApiGet.mock.calls[mockApiGet.mock.calls.length - 1][0] as string;
    expect(url).toContain('actor_id=u9');

    const callsBeforeClear = mockApiGet.mock.calls.length;
    fireEvent.change(input, { target: { value: '' } });
    await waitFor(() => {
      expect(mockApiGet.mock.calls.length).toBeGreaterThan(callsBeforeClear);
    });
    const clearedUrl = mockApiGet.mock.calls[mockApiGet.mock.calls.length - 1][0] as string;
    expect(clearedUrl).not.toContain('actor_id=');
  });

  it('filters by date range through the RangePicker', async () => {
    mockApiGet.mockResolvedValue({ items: [] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });

    const callsBefore = mockApiGet.mock.calls.length;
    fireEvent.click(document.querySelector('.ant-picker input') as HTMLElement);

    await waitFor(() => {
      expect(document.querySelector('.ant-picker-dropdown')).toBeTruthy();
    });

    const cellInners = () => Array.from(document.querySelectorAll('.ant-picker-cell-inner'));
    await waitFor(() => {
      expect(cellInners().length).toBeGreaterThan(0);
    });
    fireEvent.click(cellInners()[0]);

    await waitFor(() => {
      expect(cellInners().length).toBeGreaterThan(1);
    });
    fireEvent.click(cellInners()[1]);

    await waitFor(() => {
      expect(mockApiGet.mock.calls.length).toBeGreaterThan(callsBefore);
    });
    const url = mockApiGet.mock.calls[mockApiGet.mock.calls.length - 1][0] as string;
    expect(url).toContain('start_date=');
    expect(url).toContain('end_date=');
  });
});
