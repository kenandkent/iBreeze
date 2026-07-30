import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UserList } from './UserList';
import type { User } from '../types';

const mockUsers: User[] = [
  {
    id: '1',
    username: 'admin',
    email: 'admin@test.com',
    role: 'superadmin',
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: '2',
    username: 'user1',
    email: 'user1@test.com',
    role: 'viewer',
    is_active: false,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-01T00:00:00Z',
  },
];

describe('UserList', () => {
  it('shows loading state', () => {
    render(<UserList users={[]} loading={true} />);
    expect(screen.getByText('Loading users...')).toBeInTheDocument();
  });

  it('renders user table rows', () => {
    render(<UserList users={mockUsers} loading={false} />);
    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.getByText('user1')).toBeInTheDocument();
    expect(screen.getByText('admin@test.com')).toBeInTheDocument();
    expect(screen.getByText('user1@test.com')).toBeInTheDocument();
  });

  it('shows Active/Inactive status', () => {
    render(<UserList users={mockUsers} loading={false} />);
    const activeBadges = screen.getAllByText('Active');
    const inactiveBadges = screen.getAllByText('Inactive');
    expect(activeBadges.length).toBeGreaterThanOrEqual(1);
    expect(inactiveBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders column headers', () => {
    render(<UserList users={mockUsers} loading={false} />);
    expect(screen.getByText('Username')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Actions')).toBeInTheDocument();
  });

  it('renders edit buttons', () => {
    render(<UserList users={mockUsers} loading={false} />);
    const editButtons = screen.getAllByText('Edit');
    expect(editButtons).toHaveLength(2);
  });

  it('renders empty table', () => {
    render(<UserList users={[]} loading={false} />);
    expect(screen.getByText('Users')).toBeInTheDocument();
  });
});
