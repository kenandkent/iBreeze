import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import AdminAuditLogPage from './AdminAuditLogPage';
import * as apiClient from '../utils/apiClient';

const mockApiGet = vi.spyOn(apiClient, 'apiGet');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><AdminAuditLogPage /></TestProviders>);
}

describe('AdminAuditLogPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders page with data', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', event_type: 'auth.login', actor_id: 'u1', resource_type: 'session', resource_id: 's1', detail: { ip: '127.0.0.1' }, created_at: '2024-01-01T00:00:00Z' },
        { id: '2', event_type: 'user.create', actor_id: 'u2', resource_type: 'user', resource_id: 'u2', detail: {}, created_at: '2024-01-02T00:00:00Z' },
      ],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('auth.login')).toBeInTheDocument();
    });
    expect(screen.getByText('user.create')).toBeInTheDocument();
    expect(screen.getByText('u1')).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeInTheDocument();
    });
  });
});
