import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AdminSidebar } from './AdminSidebar';

describe('AdminSidebar', () => {
  it('renders the title', () => {
    render(<AdminSidebar />);
    expect(screen.getByText('iBreeze Admin')).toBeInTheDocument();
    expect(screen.getByText('Management Console')).toBeInTheDocument();
  });

  it('renders all navigation links', () => {
    render(<AdminSidebar />);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Skills')).toBeInTheDocument();
    expect(screen.getByText('Catalog')).toBeInTheDocument();
    expect(screen.getByText('Audit Logs')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('has correct href attributes', () => {
    render(<AdminSidebar />);
    expect(screen.getByText('Dashboard')).toHaveAttribute('href', '/dashboard');
    expect(screen.getByText('Users')).toHaveAttribute('href', '/users');
    expect(screen.getByText('Skills')).toHaveAttribute('href', '/skills');
    expect(screen.getByText('Settings')).toHaveAttribute('href', '/settings');
  });
});
