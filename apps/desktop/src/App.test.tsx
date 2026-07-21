import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';

beforeEach(() => {
  vi.restoreAllMocks();
});

vi.mock('@tauri-apps/api/core', () => ({
  invoke: async () => ({ status: 'healthy' }),
}));

vi.mock('../../services/rpcClient', () => ({
  rpcCall: async () => ({}),
  checkSidecarHealth: async () => true,
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('App', () => {
  it('renders without crashing', async () => {
    renderWithQuery(<App />);
    await waitFor(() => {
      expect(screen.getAllByText('iBreeze').length).toBeGreaterThan(0);
    });
  });
});
