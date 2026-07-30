import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';
import { useAuthStore } from '../stores/authStore';

vi.mock('../stores/authStore');

function renderWithAuth(isAuthenticated: boolean) {
  vi.mocked(useAuthStore).mockImplementation((selector: (s: { isAuthenticated: boolean; token: string | null; user: null; login: ReturnType<typeof vi.fn>; logout: ReturnType<typeof vi.fn> }) => unknown) => {
    return selector({
      isAuthenticated,
      token: isAuthenticated ? 'token' : null,
      user: null,
      login: vi.fn(),
      logout: vi.fn(),
    }) as never;
  });

  return render(
    <MemoryRouter>
      <ProtectedRoute>
        <div>Protected Content</div>
      </ProtectedRoute>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  it('renders children when authenticated', () => {
    renderWithAuth(true);
    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });

  it('does not render children when not authenticated', () => {
    renderWithAuth(false);
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });
});
