import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import SettingsPage from './SettingsPage';
import * as apiClient from '../utils/apiClient';

const mockApiGet = vi.spyOn(apiClient, 'apiGet');

function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><SettingsPage /></TestProviders>);
}

describe('SettingsPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders settings after loading', async () => {
    mockApiGet.mockResolvedValue({
      token_algorithm: 'Ed25519', token_expire_minutes: 15,
      refresh_token_expire_days: 30, log_level: 'INFO', log_json: true,
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Ed25519')).toBeInTheDocument();
    });
    expect(screen.getByText('系统设置')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('是')).toBeInTheDocument();
    expect(screen.getByText('50890')).toBeInTheDocument();
  });

  it('shows 否 for log_json false', async () => {
    mockApiGet.mockResolvedValue({
      token_algorithm: 'RSA', token_expire_minutes: 60,
      refresh_token_expire_days: 7, log_level: 'DEBUG', log_json: false,
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('否')).toBeInTheDocument();
    });
  });
});
