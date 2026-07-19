import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders status text', () => {
    render(<StatusBadge status="active" />);
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('renders with green style for active', () => {
    render(<StatusBadge status="active" />);
    const badge = screen.getByText('active');
    expect(badge.className).toContain('bg-green-100');
  });

  it('renders with gray style for inactive', () => {
    render(<StatusBadge status="inactive" />);
    const badge = screen.getByText('inactive');
    expect(badge.className).toContain('bg-gray-100');
  });

  it('renders with yellow style for pending', () => {
    render(<StatusBadge status="pending" />);
    const badge = screen.getByText('pending');
    expect(badge.className).toContain('bg-yellow-100');
  });

  it('renders with red style for error', () => {
    render(<StatusBadge status="error" />);
    const badge = screen.getByText('error');
    expect(badge.className).toContain('bg-red-100');
  });

  it('renders with default blue for unknown status', () => {
    render(<StatusBadge status="unknown_status" />);
    const badge = screen.getByText('unknown_status');
    expect(badge.className).toContain('bg-blue-100');
  });

  it('renders healthy with green', () => {
    render(<StatusBadge status="healthy" />);
    expect(screen.getByText('healthy').className).toContain('bg-green-100');
  });

  it('renders unhealthy with red', () => {
    render(<StatusBadge status="unhealthy" />);
    expect(screen.getByText('unhealthy').className).toContain('bg-red-100');
  });
});
